"""
OpenAI provider implementation with comprehensive error handling.
"""

import time
from typing import Any, Dict, List, Optional, Type

import orjson
import structlog
from pydantic import BaseModel

from ..base import AIProvider
from ..errors import AIProviderError
from ..types import AIProviderConfig, AIResponse, ErrorType, ToolSpec
from ..utils import encode_image_base64, load_file_data_from_path_async, pydantic_to_json_schema, safe_parse_json

logger = structlog.get_logger(__name__)


class OpenAIProvider(AIProvider):
    """Production-ready OpenAI provider with comprehensive error handling."""

    def __init__(self, config: AIProviderConfig):
        super().__init__(config)
        try:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=config.api_key,
                timeout=config.timeout,
                max_retries=0,  # We handle retries ourselves
            )
        except ImportError:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="OpenAI package not installed. Run: pip install openai",
                provider="openai",
                correlation_id=self.correlation_id,
            )
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=f"Failed to initialize OpenAI client: {str(e)}",
                provider="openai",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    def _build_tools(self, tools: List[ToolSpec]) -> List[Dict[str, Any]]:
        """Build OpenAI-compatible tools specification."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.json_schema,
                },
            }
            for t in (tools or [])
        ]

    async def _files_to_content(
        self, files: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """Convert files to OpenAI-compatible content."""
        content = []
        if files:
            for file_path in files:
                try:
                    file_bytes, mime_type = await load_file_data_from_path_async(
                        file_path
                    )
                    content.append(
                        {
                            "type": "file",
                            "file": {
                                "file_data": f"data:{mime_type};base64,{encode_image_base64(file_bytes)}"
                            },
                        }
                    )
                except Exception as e:
                    self.logger.error(
                        "Failed to process file", file_path=file_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing file {file_path}: {str(e)}",
                        provider="openai",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return content

    async def _images_to_content(
        self, images: Optional[List[str]], user_text: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Convert images and text to OpenAI-compatible content."""
        content = []
        if user_text:
            content.append({"type": "text", "text": user_text})

        if images:
            for image_path in images:
                try:
                    image_bytes, mime_type = await load_file_data_from_path_async(
                        image_path
                    )
                    if not mime_type.startswith("image/"):
                        raise ValueError(f"File is not an image: {mime_type}")

                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encode_image_base64(image_bytes)}"
                            },
                        }
                    )
                except Exception as e:
                    self.logger.error(
                        "Failed to process image", image_path=image_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing image {image_path}: {str(e)}",
                        provider="openai",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return content

    async def generate(
        self,
        *,
        system_instruction: Optional[str],
        user_text: Optional[str],
        images: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """Generate response using OpenAI API with comprehensive error handling."""
        model = model or self.config.model
        start_time = time.time()

        try:
            # Build messages
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})

            user_content = await self._images_to_content(images, user_text)
            user_content += await self._files_to_content(files)
            if user_content:
                messages.append({"role": "user", "content": user_content})

            # Build request
            request: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "timeout": self.config.timeout,
            }

            if tools:
                request["tools"] = self._build_tools(tools)

            if response_model is not None:
                request["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": pydantic_to_json_schema(response_model),
                        "strict": True,
                    },
                }

            # Merge vendor-specific extras
            if extra:
                request.update(extra)

            self.logger.info(
                "openai_request_starting", model=model, has_tools=bool(tools)
            )

            # Make API call with error handling
            try:
                resp = self.client.chat.completions.create(**request)
            except Exception as e:
                error_type = self._classify_openai_error(e)
                raise AIProviderError(
                    error_type=error_type,
                    message=f"OpenAI API error: {str(e)}",
                    provider="openai",
                    correlation_id=self.correlation_id,
                    original_exception=e,
                )

            # Process response
            tool_calls: List[Dict[str, Any]] = []
            text_out = None

            # Handle tool calls
            if resp.choices and resp.choices[0].message.tool_calls:
                for tool_call in resp.choices[0].message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        args = orjson.loads(tool_call.function.arguments)
                    except orjson.JSONDecodeError as e:
                        self.logger.warning(
                            "Invalid tool call arguments",
                            function=fn_name,
                            error=str(e),
                        )
                        continue

                    tool_calls.append({"name": fn_name, "arguments": args})

                    # Dispatch function
                    spec = next((t for t in (tools or []) if t.name == fn_name), None)
                    if spec:
                        try:
                            result = spec.func(args)
                            # Add assistant message with tool calls
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": tool_call.id,
                                            "type": "function",
                                            "function": {
                                                "name": fn_name,
                                                "arguments": tool_call.function.arguments,
                                            },
                                        }
                                    ],
                                }
                            )
                            # Add tool result
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": orjson.dumps(result).decode('utf-8'),
                                }
                            )

                            # Get final response
                            final_resp = self.client.chat.completions.create(
                                model=model,
                                messages=messages,
                                tools=request.get("tools"),
                                response_format=request.get("response_format"),
                                timeout=self.config.timeout,
                            )
                            resp = final_resp
                        except Exception as e:
                            self.logger.error(
                                "Tool execution failed", function=fn_name, error=str(e)
                            )
                            # Continue without failing the entire request

            # Extract final text
            if resp.choices:
                text_out = resp.choices[0].message.content

            self._request_count += 1
            processing_time = int((time.time() - start_time) * 1000)

            return AIResponse(
                text=text_out,
                structured=safe_parse_json(text_out),
                tool_calls=tool_calls,
                raw=resp,
                provider="openai",
                model=model,
                correlation_id=self.correlation_id,
                processing_time_ms=processing_time,
            )

        except AIProviderError:
            raise
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.API_ERROR,
                message=f"Unexpected OpenAI error: {str(e)}",
                provider="openai",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    def _classify_openai_error(self, error: Exception) -> ErrorType:
        """Classify OpenAI errors into standard error types."""
        error_str = str(error).lower()

        if "authentication" in error_str or "unauthorized" in error_str:
            return ErrorType.AUTHENTICATION_ERROR
        elif "rate limit" in error_str or "too many requests" in error_str:
            return ErrorType.RATE_LIMIT_ERROR
        elif "timeout" in error_str:
            return ErrorType.TIMEOUT_ERROR
        elif "quota" in error_str or "billing" in error_str:
            return ErrorType.QUOTA_EXCEEDED
        elif "invalid" in error_str or "bad request" in error_str:
            return ErrorType.INVALID_REQUEST
        else:
            return ErrorType.API_ERROR

"""
Anthropic Claude provider implementation with comprehensive error handling.
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


class AnthropicProvider(AIProvider):
    """Production-ready Anthropic provider with comprehensive error handling."""

    def __init__(self, config: AIProviderConfig):
        super().__init__(config)
        try:
            import anthropic

            self.client = anthropic.Anthropic(
                api_key=config.api_key,
                timeout=config.timeout,
                max_retries=0,  # We handle retries ourselves
            )
        except ImportError:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Anthropic package not installed. Run: pip install anthropic",
                provider="anthropic",
                correlation_id=self.correlation_id,
            )
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=f"Failed to initialize Anthropic client: {str(e)}",
                provider="anthropic",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    async def _files_to_blocks(self, files: Optional[List[str]]):
        """Convert files to Anthropic-compatible blocks."""
        blocks: List[Dict[str, Any]] = []
        if files:
            for file_path in files:
                try:
                    file_bytes, mime_type = await load_file_data_from_path_async(
                        file_path
                    )
                    blocks.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": encode_image_base64(file_bytes),
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
                        provider="anthropic",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return blocks

    async def _images_to_blocks(self, images: Optional[List[str]]):
        """Convert images to Anthropic-compatible blocks."""
        blocks: List[Dict[str, Any]] = []
        if images:
            for image_path in images:
                try:
                    image_bytes, mime_type = await load_file_data_from_path_async(
                        image_path
                    )
                    if not mime_type.startswith("image/"):
                        raise ValueError(f"File is not an image: {mime_type}")

                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": encode_image_base64(image_bytes),
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
                        provider="anthropic",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return blocks

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
        """Generate response using Anthropic API with comprehensive error handling."""
        model = model or self.config.model
        start_time = time.time()

        try:
            # Build user content
            user_content: List[Dict[str, Any]] = []
            if user_text:
                user_content.append({"type": "text", "text": user_text})

            user_content += await self._images_to_blocks(images)
            user_content += await self._files_to_blocks(files)

            messages = (
                [{"role": "user", "content": user_content}] if user_content else []
            )

            # Tools (using input_schema for Anthropic)
            tool_list = None
            if tools:
                tool_list = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.json_schema,  # Anthropic uses input_schema
                    }
                    for t in tools
                ]

            # Build request parameters
            request_params: Dict[str, Any] = {
                "model": model,
                "max_tokens": self.config.max_tokens,
                "messages": messages,
            }

            if system_instruction:
                request_params["system"] = system_instruction

            if tool_list:
                request_params["tools"] = tool_list

            # Add beta header for PDF support if files are present
            if files and any(
                (await load_file_data_from_path_async(f))[1] == "application/pdf"
                for f in files
            ):
                request_params["betas"] = ["pdfs-2024-09-25"]

            # Structured output (Anthropic supports response_format since late 2024)
            if response_model is not None:
                request_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": pydantic_to_json_schema(response_model),
                        "strict": True,
                    },
                }

            # Apply extra configurations
            if extra:
                request_params.update(extra)

            self.logger.info(
                "anthropic_request_starting", model=model, has_tools=bool(tools)
            )

            # Make API call with error handling
            try:
                resp = self.client.messages.create(**request_params)
            except Exception as e:
                error_type = self._classify_anthropic_error(e)
                raise AIProviderError(
                    error_type=error_type,
                    message=f"Anthropic API error: {str(e)}",
                    provider="anthropic",
                    correlation_id=self.correlation_id,
                    original_exception=e,
                )

            tool_calls: List[Dict[str, Any]] = []
            text_out_parts: List[str] = []

            # Handle tool calls
            for c in resp.content:
                if c.type == "tool_use":
                    fn_name = c.name
                    args = c.input or {}
                    tool_calls.append({"name": fn_name, "arguments": args})

                    # Dispatch function
                    spec = next((t for t in (tools or []) if t.name == fn_name), None)
                    if spec:
                        try:
                            result = spec.func(args)
                            # Continue conversation with tool result
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "tool_use",
                                            "id": c.id,
                                            "name": fn_name,
                                            "input": args,
                                        }
                                    ],
                                }
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": c.id,
                                            "content": orjson.dumps(result).decode('utf-8'),
                                        }
                                    ],
                                }
                            )

                            # Get final response
                            follow_resp = self.client.messages.create(
                                model=model,
                                max_tokens=self.config.max_tokens,
                                system=system_instruction,
                                tools=tool_list,
                                messages=messages,
                                betas=request_params.get("betas"),
                                response_format=request_params.get("response_format"),
                            )
                            resp = follow_resp
                        except Exception as e:
                            self.logger.error(
                                "Tool execution failed", function=fn_name, error=str(e)
                            )
                            # Continue without failing the entire request

            # Gather final text
            for c in resp.content:
                if c.type == "text":
                    text_out_parts.append(c.text)

            text_out = "\n".join(text_out_parts) if text_out_parts else None

            self._request_count += 1
            processing_time = int((time.time() - start_time) * 1000)

            return AIResponse(
                text=text_out,
                structured=safe_parse_json(text_out),
                tool_calls=tool_calls,
                raw=resp,
                provider="anthropic",
                model=model,
                correlation_id=self.correlation_id,
                processing_time_ms=processing_time,
            )

        except AIProviderError:
            raise
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.API_ERROR,
                message=f"Unexpected Anthropic error: {str(e)}",
                provider="anthropic",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    def _classify_anthropic_error(self, error: Exception) -> ErrorType:
        """Classify Anthropic errors into standard error types."""
        error_str = str(error).lower()

        if "unauthorized" in error_str or "authentication" in error_str:
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

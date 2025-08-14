"""
Google Gemini provider implementation with comprehensive error handling.
"""

import time
from typing import Any, Dict, List, Optional, Type

import structlog
from pydantic import BaseModel

from ..base import AIProvider
from ..errors import AIProviderError
from ..types import AIProviderConfig, AIResponse, ErrorType, ToolSpec
from ..utils import load_file_data_from_path_async, pydantic_to_json_schema, safe_parse_json

logger = structlog.get_logger(__name__)


class GeminiProvider(AIProvider):
    """Production-ready Gemini provider with comprehensive error handling."""

    def __init__(self, config: AIProviderConfig):
        super().__init__(config)
        try:
            from google import genai

            if not config.api_key:
                raise ValueError("GEMINI_API_KEY not provided")

            self.client = genai.Client(api_key=config.api_key)
            self.genai = genai
        except ImportError:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Google GenAI package not installed. Run: pip install google-genai",
                provider="gemini",
                correlation_id=self.correlation_id,
            )
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=f"Failed to initialize Gemini client: {str(e)}",
                provider="gemini",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    async def _files_to_parts(self, files: Optional[List[str]]):
        """Convert files to Gemini-compatible parts."""
        from google.genai import types

        parts = []
        if files:
            for file_path in files:
                try:
                    file_bytes, mime_type = await load_file_data_from_path_async(
                        file_path
                    )
                    if mime_type == "application/pdf":
                        # For PDFs, use Files API for better handling
                        try:
                            uploaded_file = self.client.files.upload(
                                file=file_path, config=dict(mime_type=mime_type)
                            )
                            parts.append(uploaded_file)
                        except Exception as e:
                            self.logger.warning(
                                "PDF upload failed, using direct bytes", error=str(e)
                            )
                            parts.append(
                                types.Part.from_bytes(
                                    data=file_bytes, mime_type=mime_type
                                )
                            )
                    else:
                        # For other files, use direct bytes
                        parts.append(
                            types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                        )
                except Exception as e:
                    self.logger.error(
                        "Failed to process file", file_path=file_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing file {file_path}: {str(e)}",
                        provider="gemini",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return parts

    async def _images_to_parts(self, images: Optional[List[str]]):
        """Convert images to Gemini-compatible parts."""
        from google.genai import types

        parts = []
        if images:
            for image_path in images:
                try:
                    image_bytes, mime_type = await load_file_data_from_path_async(
                        image_path
                    )
                    if not mime_type.startswith("image/"):
                        raise ValueError(f"File is not an image: {mime_type}")

                    parts.append(
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                    )
                except Exception as e:
                    self.logger.error(
                        "Failed to process image", image_path=image_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing image {image_path}: {str(e)}",
                        provider="gemini",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return parts

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
        """Generate response using Gemini API with comprehensive error handling."""
        from google.genai import types

        model = model or self.config.model
        start_time = time.time()

        # Tools and structured output are mutually exclusive in Gemini
        if tools and response_model:
            self.logger.warning(
                "Tools and structured output are mutually exclusive, disabling structured output"
            )
            response_model = None

        try:
            # Build tools
            tool_defs = None
            if tools:
                function_declarations = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.json_schema,
                    }
                    for t in tools
                ]
                tool_defs = [types.Tool(function_declarations=function_declarations)]

            # Build config
            config = types.GenerateContentConfig()
            if tool_defs:
                config.tools = tool_defs

            if response_model is not None:
                config.response_mime_type = "application/json"
                config.response_schema = pydantic_to_json_schema(response_model)

            # Apply extra configurations
            if extra:
                for key, value in extra.items():
                    if hasattr(config, key):
                        setattr(config, key, value)

            # Build contents
            contents = []
            if system_instruction:
                config.system_instruction = system_instruction

            user_parts = []
            if user_text:
                user_parts.append(types.Part(text=user_text))

            user_parts.extend(await self._images_to_parts(images))
            user_parts.extend(await self._files_to_parts(files))

            if user_parts:
                contents.append(types.Content(role="user", parts=user_parts))

            self.logger.info(
                "gemini_request_starting", model=model, has_tools=bool(tools)
            )

            # Make API call with error handling
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                error_type = self._classify_gemini_error(e)
                raise AIProviderError(
                    error_type=error_type,
                    message=f"Gemini API error: {str(e)}",
                    provider="gemini",
                    correlation_id=self.correlation_id,
                    original_exception=e,
                )

            tool_calls: List[Dict[str, Any]] = []

            # Handle function calls
            if hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                fn_name = fc.name
                                args = dict(fc.args or {})
                                tool_calls.append({"name": fn_name, "arguments": args})

                                # Dispatch function
                                spec = next(
                                    (t for t in (tools or []) if t.name == fn_name),
                                    None,
                                )
                                if spec:
                                    try:
                                        result = spec.func(args)
                                        # Send function response back
                                        function_response = (
                                            types.Part.from_function_response(
                                                name=fn_name,
                                                response={"result": result},
                                            )
                                        )
                                        contents.append(
                                            candidate.content
                                        )  # Add model's response
                                        contents.append(
                                            types.Content(
                                                role="user", parts=[function_response]
                                            )
                                        )

                                        # Get final response
                                        resp = self.client.models.generate_content(
                                            model=model,
                                            contents=contents,
                                            config=config,
                                        )
                                    except Exception as e:
                                        self.logger.error(
                                            "Tool execution failed",
                                            function=fn_name,
                                            error=str(e),
                                        )
                                        # Continue without failing the entire request

            text = None
            try:
                text = resp.text
            except Exception as e:
                self.logger.warning(
                    "Failed to extract text from response", error=str(e)
                )

            # Calculate estimated cost (Gemini doesn't provide token usage in response)
            self._request_count += 1
            processing_time = int((time.time() - start_time) * 1000)

            return AIResponse(
                text=text,
                structured=safe_parse_json(text),
                tool_calls=tool_calls,
                raw=resp,
                provider="gemini",
                model=model,
                correlation_id=self.correlation_id,
                processing_time_ms=processing_time,
            )

        except AIProviderError:
            raise
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.API_ERROR,
                message=f"Unexpected Gemini error: {str(e)}",
                provider="gemini",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    def _classify_gemini_error(self, error: Exception) -> ErrorType:
        """Classify Gemini errors into standard error types."""
        error_str = str(error).lower()

        if "unauthorized" in error_str or "authentication" in error_str:
            return ErrorType.AUTHENTICATION_ERROR
        elif "quota" in error_str or "limit" in error_str:
            return ErrorType.QUOTA_EXCEEDED
        elif "timeout" in error_str:
            return ErrorType.TIMEOUT_ERROR
        elif "invalid" in error_str or "bad request" in error_str:
            return ErrorType.INVALID_REQUEST
        else:
            return ErrorType.API_ERROR

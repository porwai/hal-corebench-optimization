from smolagents.models import ChatMessage, LiteLLMModel
import litellm

# Try to import ChatMessageStreamDelta, create a fallback if it doesn't exist
try:
    from smolagents.models import ChatMessageStreamDelta
except ImportError:
    # ChatMessageStreamDelta doesn't exist in this version of smolagents
    # Create a simple fallback class
    class ChatMessageStreamDelta:
        def __init__(self, content: str):
            self.content = content

# Try to import TokenUsage, create a fallback if it doesn't exist
try:
    from smolagents.models import TokenUsage
except ImportError:
    # TokenUsage doesn't exist in this version of smolagents
    # Create a simple class that matches the expected structure
    # ChatMessage likely expects an object with input_tokens and output_tokens attributes
    class TokenUsage:
        def __init__(self, input_tokens: int, output_tokens: int):
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens

class LiteLLMResponsesModel(LiteLLMModel):
    """
    A drop-in replacement for LiteLLMModel that uses the /responses API
    instead of the /chat/completions API.
    """

    def generate(
        self,
        messages,
        stop_sequences=None,
        response_format=None,
        tools_to_call_from=None,
        **kwargs,
    ):
        # Convert the messages into a single input string
        input_text = self._convert_messages_for_responses(messages)

        # Build the parameters for litellm.responses
        resp = litellm.responses(
            model=self.model_id,
            input=input_text,
            api_base=self.api_base,
            api_key=self.api_key,
            **kwargs,
        )

        # Extract output text from Responses API format
        out = ""
        if resp.output and resp.output[0].content:
            out = resp.output[0].content[0].text

        # Build a ChatMessage object SmolAgents expects
        # Extract token usage from response if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(resp, 'usage') and resp.usage:
            input_tokens = getattr(resp.usage, "prompt_tokens", 0)
            output_tokens = getattr(resp.usage, "completion_tokens", 0)
        
        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        # Create ChatMessage with token_usage
        # If token_usage is not accepted, we'll handle it via exception
        try:
            return ChatMessage(
                role="assistant",
                content=out,
                raw=resp,
                tool_calls=None,
                token_usage=token_usage,
            )
        except TypeError as e:
            # If ChatMessage doesn't accept token_usage parameter, try without it
            if "token_usage" in str(e) or "unexpected keyword" in str(e).lower():
                return ChatMessage(
                    role="assistant",
                    content=out,
                    raw=resp,
                    tool_calls=None,
                )
            raise

    def _convert_messages_for_responses(self, messages):
        """
        The Responses API expects a single text input, NOT a list of messages.
        Collapse them manually.
        """
        parts = []
        for m in messages:
            role = m["role"]
            text_blocks = [blk["text"] for blk in m["content"] if blk["type"] == "text"]
            parts.append(f"{role.upper()}: " + "\n".join(text_blocks))
        return "\n\n".join(parts)

    def generate_stream(self, messages, **kwargs):
        input_text = self._convert_messages_for_responses(messages)

        stream = litellm.responses(
            model=self.model_id,
            input=input_text,
            api_base=self.api_base,
            api_key=self.api_key,
            stream=True,
            **kwargs,
        )

        for event in stream:
            if event.type == "response.output_text.delta":
                yield ChatMessageStreamDelta(content=event.delta_text)
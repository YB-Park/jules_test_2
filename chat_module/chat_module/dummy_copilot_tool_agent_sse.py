class _CopilotToolAgentSSE:
    """
    A dummy class mimicking an internal CopilotToolAgentSSE.
    This is for local development and will be replaced by the actual
    internal module when integrated.
    """
    def __init__(self, some_string: str):
        """
        Initializes the dummy agent with a string.
        Args:
            some_string (str): A string to initialize the agent.
        """
        self.initial_string = some_string
        print(f"Dummy _CopilotToolAgentSSE initialized with: '{self.initial_string}'")

    def ask(self, query: str) -> str:
        """
        Simulates asking the agent a question.
        Args:
            query (str): The question or input string for the agent.
        Returns:
            str: A dummy response from the agent.
        """
        response = f"DummySSEAgent (init: '{self.initial_string}') | Your query: '{query}' | This is a simulated SSE stream chunk."
        # In a real SSE, this might yield multiple chunks.
        # For a simple dummy, we return a single string.
        # If you need to simulate streaming, this method could be an async generator.
        return response

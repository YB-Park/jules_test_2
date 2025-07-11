import unittest
import asyncio
from unittest.mock import patch, MagicMock

# Adjust the import path based on how you run your tests.
# If you run `python -m unittest discover` from the root directory (containing chat_module directory):
# from chat_module.utils import get_dummy_response # Removed as the function is deleted
from chat_module.session import ChatSession
from chat_module.dummy_copilot_tool_agent_sse import _CopilotToolAgentSSE

# TestChatModuleUtils class can be removed if utils.py becomes empty or only has untestable content.
# For now, let's assume utils.py might get other functions later, or we can remove this class.
# class TestChatModuleUtils(unittest.TestCase):
    # pass # No functions in utils.py to test currently

class TestChatSession(unittest.IsolatedAsyncioTestCase): # For async methods

    def setUp(self):
        # It's good practice to create a new session for each test if it has state.
        # However, ChatSession itself is recreated in tests that need a fresh one.
        # We can mock the agent here if needed across multiple tests,
        # or per-test if specific mock behaviors are required.
        pass

    async def test_initial_state(self):
        session = ChatSession()
        self.assertEqual(session.turn_count, 0)

    async def test_exit_command(self):
        session = ChatSession()
        # Mock get_user_input to simulate user typing "/exit"
        session.get_user_input = MagicMock(return_value="/exit")

        # Mock print to capture output
        with patch('builtins.print') as mock_print:
            await session.start_session()

        self.assertFalse(session.running)
        # Check if exit message was printed
        printed_texts = [str(call[0][0]) for call in mock_print.call_args_list if call[0]]
        self.assertTrue(any("Session ended by /exit command." in text for text in printed_texts))


    async def test_agent_interaction(self):
        session = ChatSession()
        test_input = "Hello Agent"

        # Mock get_user_input to return our test input then /exit
        session.get_user_input = MagicMock(side_effect=[test_input, "/exit"])

        # The session initializes its own agent. We can mock that agent's 'ask' method.
        # To do this, we can patch the _CopilotToolAgentSSE class where it's imported by the session module,
        # or mock the instance after the session is created if the agent is publicly accessible.
        # For simplicity, let's assume the agent's response is predictable or we can mock it.

        # If we want to check if the agent's ask method was called and with what:
        session.agent = MagicMock(spec=_CopilotToolAgentSSE) # Replace real agent with a mock
        expected_agent_response = f"DummySSEAgent (init: 'CLI Agent Initialized') | Your query: '{test_input}' | This is a simulated SSE stream chunk."
        session.agent.ask.return_value = expected_agent_response

        with patch('builtins.print') as mock_print:
            await session.start_session()

        self.assertEqual(session.turn_count, 1)
        session.agent.ask.assert_called_once_with(test_input)

        # Check if bot response (from agent) was printed
        printed_texts = "".join([str(call_args[0][0]) for call_args in mock_print.call_args_list])
        self.assertIn(f"Bot: {expected_agent_response}", printed_texts)

    # Note: Testing Ctrl+C and Ctrl+D behavior with prompt_toolkit's async prompt
    # within unittest can be complex due to how prompt_toolkit handles these signals
    # and its interaction with the asyncio event loop.
    # These are often better tested manually or with more specialized e2e testing tools.
    # For this example, we focus on command-based exit and basic interaction flow.

if __name__ == '__main__':
    unittest.main()

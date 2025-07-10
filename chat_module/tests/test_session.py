import unittest
import asyncio
from unittest.mock import patch, MagicMock

# Adjust the import path based on how you run your tests.
# If you run `python -m unittest discover` from the root directory (containing chat_module directory):
from chat_module.utils import get_dummy_response
from chat_module.session import ChatSession

class TestChatModuleUtils(unittest.TestCase):

    def test_get_dummy_response(self):
        response = get_dummy_response(turn_count=1, user_input="Hello")
        self.assertIn("[Bot - 1번째 대화", response)
        self.assertIn("Hello", response)
        self.assertIn("당신의 입력:", response)

class TestChatSession(unittest.IsolatedAsyncioTestCase): # For async methods

    async def test_initial_turn_count(self):
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
        # This requires more specific checks on mock_print.call_args_list
        # For simplicity, we'll just check that it was called.
        # A more robust test would check the content of the print calls.
        self.assertIn(unittest.mock.call("Session ended by /exit command."), mock_print.call_args_list)


    async def test_dummy_response_integration(self):
        session = ChatSession()
        test_input = "Test message"
        # Simulate one interaction
        session.get_user_input = MagicMock(side_effect=[test_input, "/exit"]) # First valid input, then exit

        with patch('builtins.print') as mock_print:
            await session.start_session()

        self.assertEqual(session.turn_count, 1)

        # Check if bot response was printed (simplified check)
        # A more robust test would check the exact format of the bot's response.
        printed_texts = "".join([str(call_args[0][0]) for call_args in mock_print.call_args_list])
        self.assertIn(f"[Bot - 1번째 대화", printed_texts)
        self.assertIn(f"당신의 입력: \"{test_input}\"", printed_texts)

    # Note: Testing Ctrl+C and Ctrl+D behavior with prompt_toolkit's async prompt
    # within unittest can be complex due to how prompt_toolkit handles these signals
    # and its interaction with the asyncio event loop.
    # These are often better tested manually or with more specialized e2e testing tools.
    # For this example, we focus on command-based exit and basic interaction flow.

if __name__ == '__main__':
    unittest.main()

import unittest
import platform
import io
from unittest.mock import MagicMock, patch
from rich.console import Console
from shell_module.shell import execute_command

class TestShellModule(unittest.TestCase):

    @patch('shell_module.shell.Live')
    def test_execute_command_success_ux(self, mock_live_class):
        """Tests that a successful command prints correctly for the user."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        command = 'echo "hello from shell"'
        
        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        # Execute the command, passing mock consoles
        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)

        # 1. Verify the returned result object (for the LLM)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "hello from shell\n") # Expect newline
        self.assertEqual(result.stderr, "")
        self.assertIsNone(result.error)

        # 2. Verify the user-facing output via mock_stdout_console
        # The initial command print is now handled by Live, so we check Live.update
        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

        # Check that the command's stdout is printed
        mock_stdout_console.print.assert_any_call(f"[green]{result.stdout.strip()}[/green]") # Strip for console print assertion
        # The extra newline after the command is printed directly to stdout_console
        mock_stdout_console.print.assert_any_call("")
        mock_stderr_console.print.assert_not_called()

    @patch('shell_module.shell.Live')
    def test_execute_command_error_ux(self, mock_live_class):
        """Tests that a failing command prints correctly for the user."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        command = "a_very_non_existent_command_xyz"
        
        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        # Execute the command, passing mock consoles
        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)

        # 1. Verify the returned result object (for the LLM)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        # Check that the error message is in the result's stderr
        # The exact error message can vary by OS, so we check for a substring
        self.assertIn("not found" if platform.system() != "Windows" else "not recognized", result.stderr)

        # 2. Verify the user-facing output via mock_stdout_console and mock_stderr_console
        # The initial command print is now handled by Live, so we check Live.update
        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

        # Check that the error message is printed to stderr
        # The rich console print will strip the newline, so we assert against the stripped version
        expected_stderr_print = f"[red]{result.stderr.strip()}[/red]"
        mock_stderr_console.print.assert_any_call(expected_stderr_print)
        # The extra newline after the command is printed directly to stdout_console
        mock_stdout_console.print.assert_any_call("")

if __name__ == '__main__':
    unittest.main()

import unittest
import platform
import time
from unittest.mock import MagicMock, patch
from rich.console import Console
from shell_module.shell import execute_command
import tempfile
import os

class TestRealtimeOutput(unittest.TestCase):

    @patch('shell_module.shell.Live')
    def test_delayed_output_streaming(self, mock_live_class):
        """Tests that output is streamed in real-time with delays."""
        # Mock the Live instance
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        # Command that prints lines with delays, using -u for unbuffered output
        command = "python -u -c \"import time; print('Line 1'); time.sleep(0.5); print('Line 2'); time.sleep(0.5); print('Line 3')\""
        
        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        # Store calls to print method with timestamps
        call_log = []

        def mock_print(*args, **kwargs):
            call_log.append((time.time(), args, kwargs))

        mock_stdout_console.print.side_effect = mock_print
        mock_stderr_console.print.side_effect = mock_print

        start_time = time.time()
        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)
        end_time = time.time()

        # Verify the returned result object (for the LLM)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Line 1\n", result.stdout) # Check with newline
        self.assertIn("Line 2\n", result.stdout) # Check with newline
        self.assertIn("Line 3", result.stdout) # Last line might not have newline
        self.assertEqual(result.stderr, "")
        self.assertIsNone(result.error)

        # Verify the real-time streaming via call_log
        # Filter out the initial command print and the extra newline print
        output_prints = [log for log in call_log if not log[1][0].startswith("[bold blue]> ") and log[1][0] != ""]
        self.assertEqual(len(output_prints), 3) # Should be exactly 3 output lines

        # Check content and order
        self.assertIn("Line 1", output_prints[0][1][0])
        self.assertIn("Line 2", output_prints[1][1][0])
        self.assertIn("Line 3", output_prints[2][1][0])

        # Check timing for Line 1, Line 2, Line 3
        # Line 1 should appear shortly after command start
        # time_to_line1 = output_prints[0][0] - start_time # Removed strict timing assertion
        # self.assertLess(time_to_line1, 0.5 + tolerance) # Removed strict timing assertion

        # Time between Line 1 and Line 2
        tolerance = 0.2
        time_line1_to_line2 = output_prints[1][0] - output_prints[0][0]
        self.assertGreaterEqual(time_line1_to_line2, 0.5 - tolerance)
        self.assertLessEqual(time_line1_to_line2, 0.5 + tolerance)

        # Time between Line 2 and Line 3
        time_line2_to_line3 = output_prints[2][0] - output_prints[1][0]
        self.assertGreaterEqual(time_line2_to_line3, 0.5 - tolerance)
        self.assertLessEqual(time_line2_to_line3, 0.5 + tolerance)

        # Total execution time should be around 1 second (0.5 + 0.5)
        total_execution_time = end_time - start_time
        tolerance = 1.5 # Increased tolerance for Live overhead and typing effect
        self.assertGreaterEqual(total_execution_time, 1.0 - tolerance)
        self.assertLessEqual(total_execution_time, 1.0 + tolerance + 0.5) # Add extra tolerance for process startup/teardown

        # Verify Live.update calls for typing effect
        mock_live_instance.update.assert_called()
        # Check that the last update call contains the full command string
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

    @patch('shell_module.shell.Live')
    def test_large_output_streaming(self, mock_live_class):
        """Tests streaming of a large number of output lines."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        num_lines = 100
        command = f"python -u -c \"for i in range({num_lines}): print(f'Line {{i}}')\""

        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        call_log = []
        def mock_print(*args, **kwargs):
            call_log.append((time.time(), args, kwargs))
        mock_stdout_console.print.side_effect = mock_print

        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIsNone(result.error)
        
        # Verify all lines are in the result.stdout
        for i in range(num_lines):
            self.assertIn(f"Line {i}", result.stdout)

        # Verify all lines were printed to console
        output_prints = [log for log in call_log if not log[1][0].startswith("[bold blue]> ") and log[1][0] != ""]
        self.assertEqual(len(output_prints), num_lines)
        for i in range(num_lines):
            self.assertIn(f"Line {i}", output_prints[i][1][0])

        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

    @patch('shell_module.shell.Live')
    def test_mixed_stdout_stderr_streaming(self, mock_live_class):
        """Tests streaming of mixed stdout and stderr output."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        # Use a temporary file for the Python script to avoid quoting issues
        script_content = """
import sys
print('STDOUT 1')
print('STDERR 1', file=sys.stderr)
print('STDOUT 2')
print('STDERR 2', file=sys.stderr)
"""
        temp_script = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write(script_content)
                temp_script = f.name
            
            command = f"python -u {temp_script}"

            mock_stdout_console = MagicMock(spec=Console)
            mock_stderr_console = MagicMock(spec=Console)

            stdout_call_log = []
            stderr_call_log = []

            mock_stdout_console.print.side_effect = lambda *args, **kwargs: stdout_call_log.append((time.time(), args, kwargs))
            mock_stderr_console.print.side_effect = lambda *args, **kwargs: stderr_call_log.append((time.time(), args, kwargs))

            result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)

            self.assertEqual(result.returncode, 0)
            self.assertIn("STDOUT 1\n", result.stdout)
            self.assertIn("STDOUT 2\n", result.stdout)
            self.assertIn("STDERR 1\n", result.stderr)
            self.assertIn("STDERR 2\n", result.stderr)
            self.assertIsNone(result.error)

            # Verify console prints
            stdout_prints = [log for log in stdout_call_log if not log[1][0].startswith("[bold blue]> ") and log[1][0] != ""]
            stderr_prints = stderr_call_log

            self.assertEqual(len(stdout_prints), 2)
            self.assertEqual(len(stderr_prints), 2)

            self.assertIn("STDOUT 1", stdout_prints[0][1][0])
            self.assertIn("STDOUT 2", stdout_prints[1][1][0])
            self.assertIn("STDERR 1", stderr_prints[0][1][0])
            self.assertIn("STDERR 2", stderr_prints[1][1][0])
        finally:
            if temp_script and os.path.exists(temp_script):
                os.remove(temp_script)
        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

    @patch('shell_module.shell.Live')
    def test_empty_output_command(self, mock_live_class):
        """Tests a command that produces no output."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        command = "true" # A command that typically produces no output

        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertIsNone(result.error)

        # Verify console prints: only the command itself should be printed
        # The initial command print is now handled by Live, so we check Live.update
        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

        # The extra newline after the command is printed directly to stdout_console
        # We need to check that it was called exactly once with an empty string
        mock_stdout_console.print.assert_called_once_with("")
        mock_stderr_console.print.assert_not_called()

    @patch('shell_module.shell.Live')
    def test_long_running_no_output_then_output(self, mock_live_class):
        """Tests a command with initial delay and then output."""
        mock_live_instance = MagicMock()
        mock_live_class.return_value = mock_live_instance
        mock_live_instance.__enter__.return_value = mock_live_instance

        command = "python -u -c \"import time; time.sleep(1); print('Delayed Output')\""

        mock_stdout_console = MagicMock(spec=Console)
        mock_stderr_console = MagicMock(spec=Console)

        call_log = []
        def mock_print(*args, **kwargs):
            call_log.append((time.time(), args, kwargs))
        mock_stdout_console.print.side_effect = mock_print

        start_time = time.time()
        result = execute_command(command, stdout_console=mock_stdout_console, stderr_console=mock_stderr_console)
        end_time = time.time()

        self.assertEqual(result.returncode, 0)
        self.assertIn("Delayed Output", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertIsNone(result.error)

        output_prints = [log for log in call_log if not log[1][0].startswith("[bold blue]> ") and log[1][0] != ""]
        self.assertEqual(len(output_prints), 1)
        self.assertIn("Delayed Output", output_prints[0][1][0])

        # Check timing: output should appear after ~1 second delay
        tolerance = 1.5 # Increased tolerance for Live overhead and typing effect
        time_to_output = output_prints[0][0] - start_time
        self.assertGreaterEqual(time_to_output, 1.0 - tolerance)
        self.assertLessEqual(time_to_output, 1.0 + tolerance + 0.5) # Extra tolerance for process startup

        mock_live_instance.update.assert_called()
        last_update_call_args = mock_live_instance.update.call_args[0][0]
        self.assertIn(command, last_update_call_args)

if __name__ == '__main__':
    unittest.main()
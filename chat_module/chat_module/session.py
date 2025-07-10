from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters import HasFocus, Condition
import asyncio

from .utils import get_dummy_response

class ChatSession:
    def __init__(self):
        self.turn_count = 0
        self.prompt_session = PromptSession(multiline=True)
        self.running = True

    async def get_user_input(self):
        """
        Gets multi-line user input using prompt_toolkit.
        Enter for new line, Meta+Enter (Alt+Enter or Esc then Enter) to submit.
        Ctrl+D on empty line to exit.
        """
        bindings = KeyBindings()

        # Handler for Meta+Enter or Alt+Enter - submits the input
        @bindings.add(Keys.Escape, Keys.Enter)
        @bindings.add(Keys.ControlJ) # Some terminals might send Ctrl+J for Meta+Enter
        def _(event):
            event.app.current_buffer.validate_and_handle()

        # Handler for Ctrl+C - exits the application
        @bindings.add(Keys.ControlC)
        def _(event):
            event.app.exit(result="<Ctrl+C>") # Custom result to indicate Ctrl+C

        # Handler for Ctrl+D
        @bindings.add(Keys.ControlD)
        def _(event):
            # Exit only if the buffer is empty
            if not event.app.current_buffer.text:
                event.app.exit(result="<Ctrl+D>")
            else:
                # If buffer is not empty, Ctrl+D might be used for delete char or other things
                # depending on the full keybinding setup.
                # For simplicity here, we just let it do its default or nothing.
                pass

        try:
            text = await self.prompt_session.prompt_async(
                "You: ",
                key_bindings=bindings,
                prompt_continuation="... " # For lines after the first
            )
            return text
        except EOFError: # This handles Ctrl+D on an empty line if not caught by binding
            return "<Ctrl+D>"
        except KeyboardInterrupt: # Should be caught by Ctrl+C binding, but as a fallback
             return "<Ctrl+C>"


    async def start_session(self):
        print("Welcome to the interactive chat session!")
        print("Type your message. Press Alt+Enter (or Esc then Enter) to send.")
        print("Type /exit to quit, or press Ctrl+D on an empty line.")
        print("Press Ctrl+C to exit immediately.")

        while self.running:
            try:
                user_input = await self.get_user_input()

                if user_input == "<Ctrl+C>":
                    print("\nSession ended by user (Ctrl+C).")
                    self.running = False
                    break
                if user_input == "<Ctrl+D>":
                    print("\nSession ended (Ctrl+D).")
                    self.running = False
                    break
                if user_input is None: # Should not happen with current logic, but good practice
                    print("\nSession ended (EOF).")
                    self.running = False
                    break

                user_input = user_input.strip()

                if user_input.lower() == "/exit":
                    print("Session ended by /exit command.")
                    self.running = False
                    break

                if not user_input: # If input is empty after strip (e.g. only newlines)
                    continue

                self.turn_count += 1
                bot_response = get_dummy_response(self.turn_count, user_input)
                print(f"Bot: {bot_response}")

            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                self.running = False # Stop on unexpected errors

        if not self.running and self.turn_count == 0 and user_input not in ["<Ctrl+C>", "<Ctrl+D>"] and (user_input is None or user_input.lower() != "/exit"):
             # Handles cases where loop was exited before any interaction e.g. initial Ctrl+D
             pass # Message already printed by the handler
        elif not self.running:
            pass # Exit messages are handled within the loop
        else:
            print("Session ended.")

async def main_test():
    """For testing session.py directly"""
    session = ChatSession()
    await session.start_session()

if __name__ == '__main__':
    # This allows testing session.py directly
    # In a real application, main.py would call this.
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("\nExiting...")

import asyncio
from .session import ChatSession

def main():
    """
    Main function to start the chat session.
    """
    session = ChatSession()
    try:
        asyncio.run(session.start_session())
    except KeyboardInterrupt:
        # This is a fallback if Ctrl+C is not fully handled by prompt_toolkit's event loop
        # or if it happens outside the prompt (e.g., during startup/cleanup).
        print("\nExiting application...")
    except Exception as e:
        print(f"An unexpected error occurred in main: {e}")

if __name__ == "__main__":
    main()

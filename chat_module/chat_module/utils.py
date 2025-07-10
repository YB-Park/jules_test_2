import datetime

def get_dummy_response(turn_count: int, user_input: str) -> str:
    """
    Generates a dummy response including the current time, turn count, and echoes the user input.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[Bot - {turn_count}번째 대화 - {now}]: 당신의 입력: \"{user_input}\""

import os
import asyncio
from dotenv import load_dotenv
from relay import RealtimeRelay

# Load environment variables
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print(
        "Environment variable 'OPENAI_API_KEY' is required.\n"
        "Please set it in your .env file."
    )
    exit(1)

PORT = int(os.getenv("PORT", 4000))


async def main():
    relay = RealtimeRelay(OPENAI_API_KEY)
    await relay.listen(PORT)


if __name__ == "__main__":
    asyncio.run(main())

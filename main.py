from server import TelegramBot
import asyncio
from config_reader import ConfigReader
from storageTank.stockAnalyser import StockAnalyser

# Main
if __name__ == "__main__":
    # Initiate a config_reader
    config_reader = ConfigReader()
    # Create an instance of the TelegramBot class
    # Turn off the dustbin_analyser
    dustbin_analyser = StockAnalyser(configReader = config_reader)
    bot = TelegramBot(configReader = config_reader, stock_analyser=dustbin_analyser)

    print("Setup Completed!")

    # Create the asyncio loop
    loop = asyncio.get_event_loop()

    # Scheduled loop, for the bot and the periodic task to run asynchrounously 
    loop.create_task(bot.run())
    loop.create_task(bot.periodic_task())

    # Start the loop
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("Bot stopped.")
    finally:
        loop.close()

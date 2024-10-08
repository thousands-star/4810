
import asyncio
from aiogram import Bot
from telethon import TelegramClient, events, Button
from aiogram.types import FSInputFile # use for message handler
from storageTank.stockAnalyser import *
from config_reader import ConfigReader
import time

class TelegramBot:
    """
    A Telegram bot that interacts with users and performs various tasks related to dustbin monitoring and analysis.
    """
    def __init__(self, configReader: ConfigReader, stock_analyser:StockAnalyser=None):
        # Parameter
        token = configReader.get_param('TELEGRAM', 'token')
        api_id = configReader.get_param('TELEGRAM', 'api_id')
        api_hash = configReader.get_param('TELEGRAM', 'api_hash')
        self.interval = int(configReader.get_param('TELEGRAM', 'interval'))
        self.alert_frequency = int(configReader.get_param('TELEGRAM', 'alert_frequency'))
        
        self.count = 0
        self.chat_ids = set()  # Store chat_ids of users who interact with the bot
        self.logged_in_users = set()
        self.pending_login = {}  # Track login state for each user
        ip = configReader.get_param('RASPI', 'ip')
        port_num = configReader.get_param('RASPI', 'port_num')
        self.flask_server_url = f"http://{ip}:{port_num}"

        # Set up telegram bot and dustbin analyzer
        print(token)
        self.bot = Bot(token)
        self.client = TelegramClient('bot', api_id, api_hash).start(bot_token=token)
        if(stock_analyser == None):
            self.exist_analyser = 0
        else:
            self.exist_analyser = 1
            self.data_analyser = stock_analyser

        # Register event handlers
        self.register_handlers()

    def authenticate_user(self, username, password):
        """
        Sends login credentials to the Flask server for authentication.
        """
        data = {
            "username": username,
            "password": password
        }
        try:
            response = requests.post(f"{self.flask_server_url}/login", json=data)
            return response
        except Exception as e:
            print(f"Error authenticating user: {e}")
            return None

    def add_chat_id(self, username, chat_id):
        """
        Sends the user's chat_id to the Flask server after successful login.
        """
        data = {
            "username": username,
            "chat_id": chat_id
        }
        try:
            response = requests.post(f"{self.flask_server_url}/add_chat_id", json=data)
            if response.status_code == 200:
                print(f"Chat ID for {username} successfully added to the database.")
            else:
                print(f"Failed to add chat ID for {username}.")
        except Exception as e:
            print(f"Error adding chat ID: {e}")


    """
    Handlers
    """
    def register_handlers(self):
        # Registering the event handlers
        self.client.on(events.NewMessage(pattern='Send me to real-time'))(self.realTimeGraph)
        self.client.on(events.NewMessage(pattern='/start'))(self.main_menu)
        self.client.on(events.NewMessage(pattern='Back!'))(self.main_menu)
        self.client.on(events.NewMessage(pattern='Send me a data analysis'))(self.sendDataAnalysis)
        self.client.on(events.NewMessage(pattern='Send me a graph of current fullness!'))(self.sendGraph)
        self.client.on(events.NewMessage(pattern='Login'))(self.login_handler)
        self.client.on(events.NewMessage(incoming=True))(self.handle_message)  # Catch all other messages
        self.client.on(events.NewMessage(pattern='/help'))(self.help_handler)
        self.client.on(events.NewMessage(pattern='/logout'))(self.logout_handler)
        self.client.on(events.NewMessage(pattern='/quit'))(self.quit_handler)

    async def quit_handler(self, event):
        """
        Gracefully shut down the bot on the /quit command.
        """
        user_id = event.sender_id
        await event.respond("The bot is shutting down. Goodbye!")

        # Stop the bot and disconnect the client
        await self.client.disconnect()  # Disconnect the Telegram client

        # Stop the event loop after the bot responds
        loop = asyncio.get_event_loop()
        loop.stop()

    async def logout_handler(self, event):
        """
        Log out the user by removing them from the logged_in_users set.
        """
        user_id = event.sender_id
        if user_id in self.logged_in_users:
            self.logged_in_users.remove(user_id)
            await event.respond("You have been logged out. Please log in again using /start.")
        else:
            await event.respond("You are not logged in.")

    async def help_handler(self, event):
        """
        Provide a list of available commands and their descriptions.
        """
        help_text = (
            "Here are the available commands:\n"
            "/start - Start the bot and see the main menu\n"
            "/help - Show this help message\n"
            "/logout - Log out of the bot\n"
            "\n"
            "Other commands available through buttons:\n"
            "- Real-time data\n"
            "- Data analysis\n"
            "- Graph of current fullness\n"
        )
        await event.respond(help_text)

    async def login_handler(self, event):
        user_id = event.sender_id
        self.pending_login[user_id] = {'step': 1, 'action': 'login'}
        time.sleep(1)
        await event.respond("Please enter your username:")

    async def handle_message(self, event):
        user_id = event.sender_id
        text = event.message.text.strip()
        print(text)

        # Check if the user is in the middle of the login process
        if user_id in self.pending_login:
            state = self.pending_login[user_id]
            step = state['step']

            # Step 1: Get Username
            if step == 1:
                if text == 'Login' or text == 'Sign Up':
                    return
                state['username'] = text  # Store the entered username
                state['step'] = 2  # Move to the next step (asking for password)
                await event.respond("Please enter your password:")

            # Step 2: Get Password and handle login
            elif step == 2:
                password = text
                username = state['username']

                if state['action'] == 'login':
                    # Send a request to the Raspberry Pi Flask server to check the login credentials
                    response = self.authenticate_user(username, password)
                    if response and response.status_code == 200:
                        self.logged_in_users.add(user_id)

                        # Register the user's chat_id on the server
                        self.add_chat_id(username, user_id)

                        del self.pending_login[user_id]  # Clear pending login
                        await event.respond(f"Welcome, {username}! You are now logged in.")
                        await self.main_menu(event)
                    else:
                        await event.respond("Invalid username or password. Please try again.")
                        del self.pending_login[user_id]  # Clear pending login after failed attempt

        else:
            await event.respond("Use /help to get more info.")

    # This function responsible for sending the analyzed data to the telegram bot 
    async def sendDataAnalysis(self, event):
        if event.sender_id not in self.logged_in_users:
            await self.main_menu(event)
            return
        with open('analysis.txt', 'r') as file:
            # Read the entire file content into a string
            message = file.read()
            await self.bot.send_message(event.chat_id, message)

    # This function responsible for sending the analyzed graph to the telegram bot 
    async def sendGraph(self, event):
        if event.sender_id not in self.logged_in_users:
            await self.main_menu(event)
            return
        await self.bot.send_message(event.chat_id, "Here is the graph of the current fullness:")
        file_to_send = FSInputFile("dustbin_fullness.png")
        await self.bot.send_document(event.chat_id, file_to_send)

    # This function responsible for sending a web-based real-time analyzed data 
    async def realTimeGraph(self, event):
        if event.sender_id not in self.logged_in_users:
            await self.main_menu(event)
            return
        await event.respond(
            'Link to real-time graphing:',
            buttons=[
                [Button.url('ThingSpeak', 'https://thingspeak.com/channels/2622766')],
            ]
        )

    # This function responsible for creating button to display a menu list in the telegram bot 
    async def main_menu(self, event):
        user_id = event.sender_id
        if user_id not in self.logged_in_users:
            await event.respond(
                "Welcome to the bot! Please select an option:",
                buttons=[
                    [Button.text('Login')]
                ]
            )
            return


        await event.respond(
            'Welcome to the bot! Choose an option:',
            buttons=[
                [Button.text('Send me to real-time')],
                [Button.text('Send me a data analysis')],
                [Button.text('Send me a graph of current fullness!')]
            ]
        )


    """
    Dustbin Analyser(To get the lastest data and plot)
    """
    async def periodic_task(self):
        while True:
            self.count += 1
            if self.exist_analyser == 0:
                # print("No data analyser available.")
                print("pending", self.pending_login)
                print("logged in", self.logged_in_users)
            else:
                self.data_analyser.getThingspeakData()  # Fetch the latest data
                self.data_analyser.analyseData()        # Analyse the fetched data
                
                if self.count % self.alert_frequency == 0:  # Prevent spamming alerts
                    for i in range(self.data_analyser.getDustbinNumber()):
                        fullness = self.data_analyser.getDustbinFullness()[i]
                        if fullness >= 80:
                            message = f"Alert: Dustbin {self.data_analyser.dustbin_list[i].get_tag()} is {fullness:.2f}% full. Please empty it."
                            for chat_id in self.chat_ids:
                                await self.bot.send_message(chat_id, message)
                self.data_analyser.updateThingspeak()   # Update Thingspeak with the analysed data
                self.data_analyser.plotFullness()       # Plot the latest data
            
            await asyncio.sleep(self.interval)

    """
    Bot operations 
    """
    # This function is responsible to start listening from the telegram client 
    async def run(self):
        # Start the client in the main thread
        await self.client.start()
        await self.client.run_until_disconnected()
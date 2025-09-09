"""
Configuration module for FoodPollBot with MongoDB support
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class BotConfig:
    """Telegram Bot Configuration"""
    bot_token: str
    chat_id: int
    timezone: str
    poll_start_hour: int
    poll_start_minutes: int
    poll_shift: int

@dataclass 
class MongoConfig:
    """MongoDB Configuration"""
    url: str
    db_name: str
    connection_timeout: int

@dataclass
class AppConfig:
    """Application Configuration"""
    bot: BotConfig
    mongo: MongoConfig

def load_config() -> AppConfig:
    """Load configuration from environment variables"""
    
    # Telegram Bot Configuration
    bot_config = BotConfig(
        bot_token=os.getenv('BOT_TOKEN', ''),
        chat_id=int(os.getenv('CHAT_ID', '0')),
        timezone=os.getenv('TIMEZONE', 'Asia/Yekaterinburg'),
        poll_start_hour=int(os.getenv('POLL_START_HOUR', '16')),
        poll_start_minutes=int(os.getenv('POLL_START_MINUTES', '35')),
        poll_shift=int(os.getenv('POLL_SHIFT', '1'))
    )
    
    # MongoDB Configuration
    mongo_config = MongoConfig(
        url=os.getenv('MONGO_URL', 'mongodb://localhost:27017'),
        db_name=os.getenv('MONGO_DB_NAME', 'foodpoll_bot'),
        connection_timeout=int(os.getenv('MONGO_CONNECTION_TIMEOUT', '10000'))
    )
    
    return AppConfig(
        bot=bot_config,
        mongo=mongo_config
    )
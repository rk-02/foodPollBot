#!/usr/bin/env python3
"""
Data Migration Utility for FoodPollBot
Migrates existing JSON data to MongoDB
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from infrastructure.config import load_config
from infrastructure.mongo_storage import MongoStorage
from infrastructure.menu_manager import MenuManager

async def migrate_menu_data():
    """Migrate menu data from schedule.json to MongoDB"""
    print("🔄 Starting migration to MongoDB...")
    
    # Load configuration
    config = load_config()
    
    # Initialize storage
    storage = MongoStorage(config.mongo)
    menu_manager = MenuManager(storage)
    
    try:
        # Connect to MongoDB
        await storage.connect()
        print("✅ Connected to MongoDB")
        
        # Check if menu items already exist
        existing_items = await storage.get_menu_items(active_only=False)
        if existing_items:
            response = input(f"Found {len(existing_items)} existing menu items. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print("❌ Migration cancelled")
                return
        
        # Initialize menu from schedule.json
        await menu_manager.initialize_menu_from_json("schedule.json")
        print("✅ Menu data migrated successfully")
        
        # Print statistics
        categories = await menu_manager.get_categories()
        for category in categories:
            items = await storage.get_menu_items(category=category)
            print(f"  📋 {category}: {len(items)} items")
        
        print("\n🎉 Migration completed successfully!")
        print("\n📋 Next steps:")
        print("1. Update your .env file with correct MongoDB connection details")
        print("2. Make sure MongoDB is running")
        print("3. Test the bot with: python add_poll_by_day.py")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    finally:
        await storage.disconnect()
        print("🔌 Disconnected from MongoDB")
    
    return True

async def test_mongodb_connection():
    """Test MongoDB connection"""
    print("🔍 Testing MongoDB connection...")
    
    config = load_config()
    storage = MongoStorage(config.mongo)
    
    try:
        await storage.connect()
        is_healthy = await storage.health_check()
        
        if is_healthy:
            print("✅ MongoDB connection successful")
            
            # Test basic operations
            test_item_id = await storage.save_menu_item(
                category="Test",
                name="Test Item",
                description="Test description"
            )
            print("✅ Write operation successful")
            
            # Clean up test data
            await storage.update_menu_item(test_item_id, is_active=False)
            print("✅ Update operation successful")
            
        else:
            print("❌ MongoDB health check failed")
            return False
            
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False
    finally:
        await storage.disconnect()
    
    return True

async def show_config():
    """Show current configuration"""
    print("⚙️ Current Configuration:")
    config = load_config()
    
    print(f"MongoDB URL: {config.mongo.url}")
    print(f"Database Name: {config.mongo.db_name}")
    print(f"Connection Timeout: {config.mongo.connection_timeout}ms")
    print(f"Bot Token: {config.bot.bot_token[:10]}..." if config.bot.bot_token else "Bot Token: Not set")
    print(f"Chat ID: {config.bot.chat_id}")
    print(f"Timezone: {config.bot.timezone}")
    print(f"Poll Time: {config.bot.poll_start_hour:02d}:{config.bot.poll_start_minutes:02d}")

def print_help():
    """Print help information"""
    print("🤖 FoodPollBot MongoDB Migration Utility")
    print("\nUsage: python migrate_to_mongo.py [command]")
    print("\nCommands:")
    print("  migrate     - Migrate menu data from schedule.json to MongoDB")
    print("  test        - Test MongoDB connection")
    print("  config      - Show current configuration")
    print("  help        - Show this help message")
    print("\nEnvironment:")
    print("  Make sure your .env file is configured with MongoDB settings:")
    print("  - MONGO_URL=mongodb://localhost:27017")
    print("  - MONGO_DB_NAME=foodpoll_bot")
    print("  - MONGO_CONNECTION_TIMEOUT=10000")

async def main():
    """Main migration function"""
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if command == "migrate":
        success = await migrate_menu_data()
        sys.exit(0 if success else 1)
    elif command == "test":
        success = await test_mongodb_connection()
        sys.exit(0 if success else 1)
    elif command == "config":
        await show_config()
    elif command == "help":
        print_help()
    else:
        print(f"❌ Unknown command: {command}")
        print_help()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
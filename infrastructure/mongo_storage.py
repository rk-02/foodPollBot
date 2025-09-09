"""
MongoDB Storage Implementation for FoodPollBot
"""
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import IndexModel
from .config import MongoConfig
import logging

logger = logging.getLogger(__name__)

class MongoStorage:
    """MongoDB storage implementation for food poll bot"""
    
    def __init__(self, config: MongoConfig):
        self.config = config
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self._collections: Dict[str, AsyncIOMotorCollection] = {}
        
    async def connect(self) -> None:
        """Establish connection to MongoDB"""
        try:
            self.client = AsyncIOMotorClient(
                self.config.url,
                serverSelectionTimeoutMS=self.config.connection_timeout
            )
            
            # Test connection
            await self.client.admin.command('ping')
            logger.info("Connected to MongoDB successfully")
            
            self.db = self.client[self.config.db_name]
            await self._setup_collections()
            await self._create_indexes()
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    async def _setup_collections(self) -> None:
        """Setup collection references"""
        self._collections = {
            'menu_items': self.db.menu_items,
            'polls': self.db.polls,
            'user_votes': self.db.user_votes,
            'poll_results': self.db.poll_results
        }
    
    async def _create_indexes(self) -> None:
        """Create database indexes for better performance"""
        try:
            # Menu items indexes
            await self._collections['menu_items'].create_indexes([
                IndexModel([('category', 1), ('is_active', 1)]),
                IndexModel([('display_order', 1)])
            ])
            
            # Polls indexes
            await self._collections['polls'].create_indexes([
                IndexModel([('poll_date', 1)]),
                IndexModel([('category', 1), ('poll_date', 1)])
            ])
            
            # User votes indexes
            await self._collections['user_votes'].create_indexes([
                IndexModel([('poll_id', 1), ('user_id', 1)]),
                IndexModel([('user_id', 1), ('voted_at', -1)]),
                IndexModel([('poll_id', 1)])
            ])
            
            # Poll results indexes
            await self._collections['poll_results'].create_indexes([
                IndexModel([('date', 1)])
            ])
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
    
    # Menu Items Management
    async def save_menu_item(self, category: str, name: str, description: str = "", 
                           display_order: int = 0) -> str:
        """Save a menu item"""
        doc = {
            'category': category,
            'name': name,
            'description': description,
            'is_active': True,
            'display_order': display_order,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = await self._collections['menu_items'].insert_one(doc)
        return str(result.inserted_id)
    
    async def get_menu_items(self, category: Optional[str] = None, 
                           active_only: bool = True) -> List[Dict]:
        """Get menu items by category"""
        query = {}
        if category:
            query['category'] = category
        if active_only:
            query['is_active'] = True
            
        cursor = self._collections['menu_items'].find(query).sort('display_order', 1)
        return await cursor.to_list(length=None)
    
    async def update_menu_item(self, item_id: str, **kwargs) -> bool:
        """Update menu item"""
        kwargs['updated_at'] = datetime.utcnow()
        result = await self._collections['menu_items'].update_one(
            {'_id': item_id}, 
            {'$set': kwargs}
        )
        return result.modified_count > 0
    
    # Poll Management
    async def save_poll(self, poll_id: str, category: str, poll_date: str, 
                       question: str, options: List[str], is_anonymous: bool = False) -> None:
        """Save poll information"""
        options_list = []
        for i, option_text in enumerate(options):
            options_list.append({
                'index': i,
                'text': option_text,
                'voter_count': 0
            })
        
        doc = {
            '_id': poll_id,
            'category': category,
            'poll_date': poll_date,
            'question': question,
            'options': options_list,
            'is_anonymous': is_anonymous,
            'is_closed': False,
            'total_voter_count': 0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        await self._collections['polls'].replace_one(
            {'_id': poll_id}, 
            doc, 
            upsert=True
        )
    
    async def get_poll(self, poll_id: str) -> Optional[Dict]:
        """Get poll by ID"""
        return await self._collections['polls'].find_one({'_id': poll_id})
    
    async def get_polls_by_date(self, poll_date: str) -> List[Dict]:
        """Get all polls for a specific date"""
        cursor = self._collections['polls'].find({'poll_date': poll_date})
        return await cursor.to_list(length=None)
    
    async def update_poll_votes(self, poll_id: str, option_votes: List[int], 
                              total_votes: int) -> None:
        """Update poll vote counts"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return
            
        # Update vote counts for each option
        for i, vote_count in enumerate(option_votes):
            if i < len(poll['options']):
                poll['options'][i]['voter_count'] = vote_count
        
        await self._collections['polls'].update_one(
            {'_id': poll_id},
            {
                '$set': {
                    'options': poll['options'],
                    'total_voter_count': total_votes,
                    'updated_at': datetime.utcnow()
                }
            }
        )
    
    # User Votes Management
    async def save_user_vote(self, poll_id: str, user_id: int, user_name: str,
                           option_indices: List[int], option_texts: List[str]) -> None:
        """Save user vote"""
        doc = {
            'poll_id': poll_id,
            'user_id': user_id,
            'user_name': user_name,
            'option_indices': option_indices,
            'option_texts': option_texts,
            'voted_at': datetime.utcnow()
        }
        
        # Replace existing vote for this poll and user
        await self._collections['user_votes'].replace_one(
            {'poll_id': poll_id, 'user_id': user_id},
            doc,
            upsert=True
        )
    
    async def get_user_votes(self, poll_id: str, user_id: Optional[int] = None) -> List[Dict]:
        """Get user votes for a poll"""
        query = {'poll_id': poll_id}
        if user_id is not None:
            query['user_id'] = user_id
            
        cursor = self._collections['user_votes'].find(query)
        return await cursor.to_list(length=None)
    
    # Poll Results Management
    async def save_poll_results(self, date: str, results_data: Dict) -> None:
        """Save aggregated poll results for a date"""
        doc = {
            '_id': date,
            'date': date,
            'categories': results_data.get('categories', {}),
            'user_combinations': results_data.get('user_combinations', {}),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        await self._collections['poll_results'].replace_one(
            {'_id': date},
            doc,
            upsert=True
        )
    
    async def get_poll_results(self, date: str) -> Optional[Dict]:
        """Get poll results for a specific date"""
        return await self._collections['poll_results'].find_one({'_id': date})
    
    async def update_user_combination(self, date: str, user_id: int, 
                                    category: str, choices: List[str]) -> None:
        """Update user's food combination choices for a date"""
        # Get existing results or create new
        results = await self.get_poll_results(date)
        if not results:
            results = {
                'date': date,
                'categories': {},
                'user_combinations': {},
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
        
        # Update user combinations
        if 'user_combinations' not in results:
            results['user_combinations'] = {}
            
        user_key = str(user_id)
        if user_key not in results['user_combinations']:
            results['user_combinations'][user_key] = {}
            
        results['user_combinations'][user_key][category] = choices
        results['updated_at'] = datetime.utcnow()
        
        await self.save_poll_results(date, results)
    
    # Database utilities
    async def health_check(self) -> bool:
        """Check if database connection is healthy"""
        try:
            await self.client.admin.command('ping')
            return True
        except Exception:
            return False
    
    async def clear_old_data(self, days_to_keep: int = 30) -> None:
        """Clear old poll data (utility method)"""
        cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date - timedelta(days=days_to_keep)
        
        # Remove old votes
        await self._collections['user_votes'].delete_many({
            'voted_at': {'$lt': cutoff_date}
        })
        
        logger.info(f"Cleaned data older than {days_to_keep} days")
# ffmc/monitoring/notifier.py
"""
Webhook notification system for Discord, Slack, etc.
Sends alerts on conversion completion, errors, and milestones
"""

import aiohttp
import json
from typing import Optional, Dict, Any
from datetime import datetime

from ffmc.monitoring.logger import get_logger

logger = get_logger('notifier')


class Notifier:
    """
    Sends notifications via webhooks
    
    Supports:
    - Discord webhooks
    - Slack webhooks
    - Generic JSON webhooks
    """
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def send(
        self,
        message: str,
        level: str = 'info',
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Send notification via webhook
        
        Args:
            message: Notification message
            level: Message level (info, success, warning, error)
            data: Optional additional data
        """
        if not self.webhook_url:
            logger.debug("No webhook URL configured, skipping notification")
            return
        
        try:
            await self._ensure_session()
            
            # Detect webhook type and format accordingly
            if 'discord' in self.webhook_url.lower():
                payload = self._format_discord(message, level, data)
            elif 'slack' in self.webhook_url.lower():
                payload = self._format_slack(message, level, data)
            else:
                payload = self._format_generic(message, level, data)
            
            async with self.session.post(
                self.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status not in (200, 204):
                    logger.warning(
                        f"Webhook request failed with status {response.status}"
                    )
                else:
                    logger.debug("Notification sent successfully")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Failed to send notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {e}")
    
    def _format_discord(
        self,
        message: str,
        level: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict:
        """Format payload for Discord webhook"""
        # Color codes for different levels
        colors = {
            'info': 0x3498db,      # Blue
            'success': 0x2ecc71,   # Green
            'warning': 0xf39c12,   # Orange
            'error': 0xe74c3c      # Red
        }
        
        embed = {
            'title': f'FFMC - {level.upper()}',
            'description': message,
            'color': colors.get(level, 0x95a5a6),
            'timestamp': datetime.utcnow().isoformat(),
            'footer': {
                'text': 'FFMC Video Converter'
            }
        }
        
        if data:
            embed['fields'] = [
                {'name': key, 'value': str(value), 'inline': True}
                for key, value in data.items()
            ]
        
        return {
            'username': 'FFMC Bot',
            'embeds': [embed]
        }
    
    def _format_slack(
        self,
        message: str,
        level: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict:
        """Format payload for Slack webhook"""
        # Emoji for different levels
        emoji = {
            'info': ':information_source:',
            'success': ':white_check_mark:',
            'warning': ':warning:',
            'error': ':x:'
        }
        
        blocks = [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f"{emoji.get(level, '')} *FFMC - {level.upper()}*\n{message}"
                }
            }
        ]
        
        if data:
            fields = [
                {
                    'type': 'mrkdwn',
                    'text': f"*{key}:*\n{value}"
                }
                for key, value in data.items()
            ]
            blocks.append({
                'type': 'section',
                'fields': fields
            })
        
        return {
            'username': 'FFMC Bot',
            'blocks': blocks
        }
    
    def _format_generic(
        self,
        message: str,
        level: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict:
        """Format generic JSON payload"""
        payload = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message,
            'source': 'FFMC'
        }
        
        if data:
            payload['data'] = data
        
        return payload
    
    async def notify_start(self, total_files: int):
        """Send notification when conversion starts"""
        await self.send(
            f"Starting conversion of {total_files} videos",
            level='info',
            data={'total_files': total_files}
        )
    
    async def notify_completion(
        self,
        successful: int,
        failed: int,
        skipped: int,
        duration: str,
        space_saved: str
    ):
        """Send notification when conversion completes"""
        if failed > 0:
            level = 'warning'
            title = "Conversion completed with errors"
        else:
            level = 'success'
            title = "Conversion completed successfully"
        
        message = (
            f"{title}\n\n"
            f"Successful: {successful}\n"
            f"Failed: {failed}\n"
            f"Skipped: {skipped}\n"
            f"Duration: {duration}\n"
            f"Space saved: {space_saved}"
        )
        
        await self.send(
            message,
            level=level,
            data={
                'successful': successful,
                'failed': failed,
                'skipped': skipped,
                'duration': duration,
                'space_saved': space_saved
            }
        )
    
    async def notify_error(self, error_message: str, file_name: Optional[str] = None):
        """Send error notification"""
        message = f"Conversion error"
        if file_name:
            message += f" for {file_name}"
        message += f": {error_message}"
        
        await self.send(message, level='error')
    
    async def notify_milestone(self, completed: int, total: int):
        """Send milestone notification (e.g., 50% complete)"""
        percentage = (completed / total) * 100 if total > 0 else 0
        
        # Send notification at 25%, 50%, 75%
        if percentage in [25, 50, 75]:
            await self.send(
                f"Progress update: {completed}/{total} videos converted ({percentage:.0f}%)",
                level='info',
                data={
                    'completed': completed,
                    'total': total,
                    'percentage': f"{percentage:.0f}%"
                }
            )
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.session and not self.session.closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.session.close())
                else:
                    loop.run_until_complete(self.session.close())
            except:
                pass
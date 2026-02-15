"""
Configuration management for Interactive Brokers wrapper.

This module handles loading and managing configuration from YAML files
and environment variables, with validation and default values.
"""

import os
import yaml
import logging
from typing import Any, Optional, Dict
from pathlib import Path

from .exceptions import ConfigurationException
from .models import ConnectionConfig

logger = logging.getLogger(__name__)


class Config:
    """
    Configuration manager supporting YAML files and environment variables.

    Configuration priority (highest to lowest):
    1. Environment variables
    2. Config file
    3. Default values
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to YAML config file (optional)
        """
        self._config: Dict[str, Any] = {}
        self._load_defaults()

        # Load config file if provided
        if config_path:
            self._load_config_file(config_path)
        else:
            # Try to load default config file
            default_config = Path(__file__).parent.parent / 'config' / 'default_config.yaml'
            if default_config.exists():
                self._load_config_file(str(default_config))

        # Override with environment variables
        self._load_env_vars()

    def _load_defaults(self):
        """Load default configuration values."""
        self._config = {
            'ib_connection': {
                'host': '127.0.0.1',
                'port': 7497,
                'client_id': 1,
                'timeout': 10,
                'readonly': False
            },
            'market_data': {
                'rate_limit_requests': 50,
                'rate_limit_window': 600,
                'default_duration': '1 D',
                'default_bar_size': '1 min',
                'default_what_to_show': 'TRADES'
            },
            'portfolio': {
                'auto_subscribe_updates': True,
                'update_interval': 1.0
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'file': 'logs/ib_wrapper.log',
                'console': True
            }
        }

    def _load_config_file(self, config_path: str):
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML config file

        Raises:
            ConfigurationException: If config file is invalid
        """
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)

            if file_config:
                self._merge_config(self._config, file_config)
                logger.info(f"Loaded configuration from {config_path}")

        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}")
        except yaml.YAMLError as e:
            raise ConfigurationException(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigurationException(f"Error loading config file: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # IB Connection settings
        if os.getenv('IB_HOST'):
            self._config['ib_connection']['host'] = os.getenv('IB_HOST')

        if os.getenv('IB_PORT'):
            try:
                self._config['ib_connection']['port'] = int(os.getenv('IB_PORT'))
            except ValueError:
                logger.warning("Invalid IB_PORT environment variable, using default")

        if os.getenv('IB_CLIENT_ID'):
            try:
                self._config['ib_connection']['client_id'] = int(os.getenv('IB_CLIENT_ID'))
            except ValueError:
                logger.warning("Invalid IB_CLIENT_ID environment variable, using default")

        if os.getenv('IB_TIMEOUT'):
            try:
                self._config['ib_connection']['timeout'] = int(os.getenv('IB_TIMEOUT'))
            except ValueError:
                logger.warning("Invalid IB_TIMEOUT environment variable, using default")

        if os.getenv('IB_READONLY'):
            self._config['ib_connection']['readonly'] = os.getenv('IB_READONLY').lower() in ('true', '1', 'yes')

        # Logging settings
        if os.getenv('LOG_LEVEL'):
            self._config['logging']['level'] = os.getenv('LOG_LEVEL')

        if os.getenv('LOG_FILE'):
            self._config['logging']['file'] = os.getenv('LOG_FILE')

        # Account
        if os.getenv('IB_ACCOUNT'):
            self._config['ib_account'] = os.getenv('IB_ACCOUNT')

    def _merge_config(self, base: Dict, override: Dict):
        """
        Recursively merge override config into base config.

        Args:
            base: Base configuration dictionary
            override: Override configuration dictionary
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.

        Args:
            key: Configuration key in dot notation (e.g., 'ib_connection.host')
            default: Default value if key not found

        Returns:
            Configuration value or default

        Examples:
            >>> config.get('ib_connection.host')
            '127.0.0.1'
            >>> config.get('ib_connection.port')
            7497
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_connection_config(self) -> ConnectionConfig:
        """
        Get connection configuration as ConnectionConfig object.

        Returns:
            ConnectionConfig instance
        """
        return ConnectionConfig(
            host=self.get('ib_connection.host', '127.0.0.1'),
            port=self.get('ib_connection.port', 7497),
            client_id=self.get('ib_connection.client_id', 1),
            timeout=self.get('ib_connection.timeout', 10),
            readonly=self.get('ib_connection.readonly', False)
        )

    def validate(self):
        """
        Validate configuration.

        Raises:
            ConfigurationException: If configuration is invalid
        """
        # Validate required fields
        if not self.get('ib_connection.host'):
            raise ConfigurationException("Missing required config: ib_connection.host")

        if not isinstance(self.get('ib_connection.port'), int):
            raise ConfigurationException("Invalid config: ib_connection.port must be integer")

        if not isinstance(self.get('ib_connection.client_id'), int):
            raise ConfigurationException("Invalid config: ib_connection.client_id must be integer")

        # Validate port range
        port = self.get('ib_connection.port')
        if port < 1 or port > 65535:
            raise ConfigurationException(f"Invalid port number: {port}")

        logger.info("Configuration validated successfully")

    def to_dict(self) -> Dict[str, Any]:
        """
        Get full configuration as dictionary.

        Returns:
            Configuration dictionary
        """
        return self._config.copy()

    def __repr__(self) -> str:
        """String representation of config."""
        return f"Config({self._config})"

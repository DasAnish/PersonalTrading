"""
Strategy Loader for YAML-based strategy definitions.

Loads strategy configurations from YAML files and builds executable strategy instances.
Supports composable strategies where overlays wrap underlying strategies.

Usage:
    loader = StrategyLoader()

    # Load single strategy
    strategy = loader.load_strategy('trend_following')

    # Load composed strategy with overlays
    strategy = loader.load_composed_strategy('trend_with_vol_12')

    # List available strategies
    markets = loader.list_strategies('market')
    allocations = loader.list_strategies('allocation')
    overlays = loader.list_strategies('overlay')
"""

from __future__ import annotations
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import importlib

from strategies.base import ExecutableStrategy, MarketStrategy, AllocationStrategy, OverlayStrategy


class StrategyLoader:
    """Load and build strategies from YAML configuration files."""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize strategy loader.

        Args:
            config_dir: Path to strategy_definitions directory.
                       Defaults to strategy_definitions/ in project root.
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / 'strategy_definitions'

        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}  # Cache loaded strategies

        if not self.config_dir.exists():
            raise FileNotFoundError(
                f"Strategy definitions directory not found: {self.config_dir}"
            )

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Load YAML file and return parsed content."""
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    def _load_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a JSON or YAML definition file."""
        with open(file_path, 'r') as f:
            if file_path.suffix == '.json':
                return json.load(f)
            return yaml.safe_load(f)

    def _find_strategy_file(self, strategy_key: str) -> Optional[Path]:
        """
        Find strategy definition file by key.

        Handles path-based refs like "assets/vusa" (maps directly to
        strategy_definitions/assets/vusa.json) and simple keys like
        "equal_weight" (searched across all subdirectories).

        Prefers .json over .yaml when both exist.

        Args:
            strategy_key: Strategy identifier, e.g. 'equal_weight' or 'assets/vusa'

        Returns:
            Path to file if found, None otherwise
        """
        # Path-based ref: look directly under config_dir
        if '/' in strategy_key:
            for ext in ('.json', '.yaml'):
                path = self.config_dir / f"{strategy_key}{ext}"
                if path.exists():
                    return path
            return None

        # Simple key: search all subdirectories, JSON first
        for ext in ('.json', '.yaml'):
            for subdir in self.config_dir.iterdir():
                if not subdir.is_dir():
                    continue
                file_path = subdir / f"{strategy_key}{ext}"
                if file_path.exists():
                    return file_path

        return None

    def load_definition(self, strategy_key: str) -> Dict[str, Any]:
        """
        Load strategy definition from YAML file.

        Args:
            strategy_key: Strategy identifier

        Returns:
            Parsed YAML content as dictionary

        Raises:
            FileNotFoundError: If strategy definition file not found
        """
        if strategy_key in self._cache:
            return self._cache[strategy_key]

        file_path = self._find_strategy_file(strategy_key)
        if file_path is None:
            raise FileNotFoundError(
                f"Strategy definition not found: {strategy_key}"
            )

        definition = self._load_file(file_path)
        self._cache[strategy_key] = definition
        return definition

    def _get_class(self, class_name: str):
        """
        Get strategy class by name.

        Args:
            class_name: Fully qualified class name or simple class name

        Returns:
            Strategy class

        Raises:
            ImportError: If class cannot be imported
        """
        # Try simple import from strategies module first
        try:
            import strategies
            return getattr(strategies, class_name)
        except (ImportError, AttributeError):
            pass

        # Try fully qualified import
        if '.' in class_name:
            module_name, cls_name = class_name.rsplit('.', 1)
            try:
                module = importlib.import_module(module_name)
                return getattr(module, cls_name)
            except (ImportError, AttributeError):
                pass

        raise ImportError(f"Cannot import class: {class_name}")

    def _build_strategy_from_def(self, definition: Dict[str, Any]) -> ExecutableStrategy:
        """
        Recursively build a strategy from an inline definition dict.

        Handles all types:
          - "asset"      → AssetStrategy(**parameters)
          - "allocation" → StrategyClass(underlying=[...], **parameters)
          - "composed"   → StrategyClass(underlying=<recursive>, **parameters)
          - "overlay"    → StrategyClass(underlying=<recursive>, **parameters)
          - "market"     → legacy YAML market class

        The "underlying" field in allocation definitions is a list of either
        string refs (e.g. "assets/vusa") or inline dicts.  In composed/overlay
        definitions it is a single string ref or inline dict.

        Args:
            definition: Parsed definition dictionary

        Returns:
            Instantiated strategy
        """
        strategy_type = definition.get('type')
        class_name = definition.get('class')
        params = definition.get('parameters', {}).copy()

        if strategy_type == 'asset':
            strategy_class = self._get_class(class_name)
            return strategy_class(**params)

        if strategy_type in ('allocation',):
            strategy_class = self._get_class(class_name)
            underlying_refs = definition.get('underlying', [])
            underlying_list = []
            for ref in underlying_refs:
                if isinstance(ref, str):
                    underlying_def = self.load_definition(ref)
                    underlying_list.append(self._build_strategy_from_def(underlying_def))
                elif isinstance(ref, dict):
                    underlying_list.append(self._build_strategy_from_def(ref))
            params['underlying'] = underlying_list
            return strategy_class(**params)

        if strategy_type in ('composed', 'overlay'):
            strategy_class = self._get_class(class_name)
            underlying_ref = definition.get('underlying')
            if underlying_ref is not None:
                if isinstance(underlying_ref, str):
                    underlying_def = self.load_definition(underlying_ref)
                    params['underlying'] = self._build_strategy_from_def(underlying_def)
                elif isinstance(underlying_ref, dict):
                    params['underlying'] = self._build_strategy_from_def(underlying_ref)
            return strategy_class(**params)

        if strategy_type == 'market':
            strategy_class = self._get_class(class_name)
            return strategy_class(**params)

        raise ValueError(f"Unknown strategy type: {strategy_type!r}")

    def build_market_strategy(
        self, strategy_key: str
    ) -> MarketStrategy:
        """
        Build market strategy instance from definition.

        Args:
            strategy_key: Market strategy identifier

        Returns:
            Instantiated MarketStrategy

        Raises:
            ValueError: If definition is not a market strategy
        """
        definition = self.load_definition(strategy_key)

        if definition.get('type') != 'market':
            raise ValueError(
                f"Expected market strategy, got: {definition.get('type')}"
            )

        class_name = definition['class']
        strategy_class = self._get_class(class_name)
        params = definition.get('parameters', {})

        return strategy_class(**params)

    def build_allocation_strategy(
        self, strategy_key: str
    ) -> AllocationStrategy:
        """
        Build allocation strategy instance from definition.

        Resolves market reference and builds underlying market strategy.

        Args:
            strategy_key: Allocation strategy identifier

        Returns:
            Instantiated AllocationStrategy

        Raises:
            ValueError: If definition is not an allocation strategy
        """
        definition = self.load_definition(strategy_key)

        if definition.get('type') != 'allocation':
            raise ValueError(
                f"Expected allocation strategy, got: {definition.get('type')}"
            )

        class_name = definition['class']
        strategy_class = self._get_class(class_name)
        params = definition.get('parameters', {}).copy()

        # Build underlying market strategy
        market_key = definition.get('market')
        if market_key:
            underlying_market = self.build_market_strategy(market_key)
            params['underlying'] = underlying_market

        return strategy_class(**params)

    def build_overlay_strategy(
        self, strategy_key: str, underlying: Optional[ExecutableStrategy] = None
    ) -> OverlayStrategy:
        """
        Build overlay strategy instance from definition.

        Resolves underlying strategy reference if not provided.

        Args:
            strategy_key: Overlay strategy identifier
            underlying: Optional underlying strategy. If not provided, will load from definition.

        Returns:
            Instantiated OverlayStrategy

        Raises:
            ValueError: If definition is not an overlay strategy
        """
        definition = self.load_definition(strategy_key)

        if definition.get('type') != 'overlay':
            raise ValueError(
                f"Expected overlay strategy, got: {definition.get('type')}"
            )

        class_name = definition['class']
        strategy_class = self._get_class(class_name)
        params = definition.get('parameters', {}).copy()

        # Resolve underlying strategy if not provided
        if underlying is None:
            underlying_key = definition.get('underlying')
            if underlying_key:
                underlying = self.build_allocation_strategy(underlying_key)
            else:
                raise ValueError(
                    f"Overlay strategy '{strategy_key}' requires underlying strategy"
                )

        params['underlying'] = underlying
        return strategy_class(**params)

    def build_composed_strategy(
        self, strategy_key: str
    ) -> ExecutableStrategy:
        """
        Build composed strategy with multiple overlay layers.

        Composition works bottom-up:
        1. Start with allocation strategy (from overlay's 'underlying' field)
        2. Apply first overlay
        3. Apply second overlay to the result
        4. Continue through all layers

        Args:
            strategy_key: Composed strategy identifier

        Returns:
            Final strategy with all overlays applied

        Raises:
            ValueError: If definition is not a composed strategy
        """
        definition = self.load_definition(strategy_key)

        if definition.get('type') != 'composed':
            raise ValueError(
                f"Expected composed strategy, got: {definition.get('type')}"
            )

        layers = definition.get('layers', [])
        if not layers:
            raise ValueError(f"Composed strategy '{strategy_key}' has no layers")

        # Build first layer (allocation strategy with underlying)
        first_layer_key = layers[0]
        strategy = self.build_overlay_strategy(first_layer_key)

        # Apply remaining overlay layers
        for layer_key in layers[1:]:
            strategy = self.build_overlay_strategy(layer_key, underlying=strategy)

        return strategy

    def build_strategy(self, strategy_key: str) -> ExecutableStrategy:
        """
        Build strategy from definition (auto-detect type).

        Automatically determines type and builds appropriate strategy.

        Args:
            strategy_key: Strategy identifier

        Returns:
            Instantiated strategy

        Raises:
            ValueError: If strategy type is unknown
        """
        definition = self.load_definition(strategy_key)
        return self._build_strategy_from_def(definition)

    def list_strategies(self, strategy_type: Optional[str] = None) -> Dict[str, str]:
        """
        List available strategy definitions.

        Args:
            strategy_type: Filter by type ('market', 'allocation', 'overlay', 'composed').
                          If None, returns all strategies.

        Returns:
            Dict mapping strategy_key to description
        """
        # Collect best file per stem: JSON takes priority over YAML
        best_files: Dict[str, Path] = {}
        for file_path in self.config_dir.rglob('*.json'):
            best_files[file_path.stem] = file_path
        for file_path in self.config_dir.rglob('*.yaml'):
            if file_path.stem not in best_files:
                best_files[file_path.stem] = file_path

        strategies = {}
        for stem, file_path in best_files.items():
            try:
                definition = self._load_file(file_path)
                file_type = definition.get('type')

                if strategy_type and file_type != strategy_type:
                    continue

                description = definition.get('description', '').split('\n')[0]
                strategies[stem] = description

            except Exception as e:
                print(f"Warning: Could not parse {file_path}: {e}")
                continue

        return strategies

    def print_strategy_info(self, strategy_key: str) -> None:
        """
        Print detailed information about a strategy.

        Args:
            strategy_key: Strategy identifier
        """
        definition = self.load_definition(strategy_key)

        print(f"\nStrategy: {strategy_key}")
        print(f"Type: {definition.get('type')}")
        print(f"Class: {definition.get('class')}")
        print(f"\nDescription:")
        print(f"  {definition.get('description', 'N/A')}")

        params = definition.get('parameters', {})
        if params:
            print(f"\nParameters:")
            for key, value in params.items():
                print(f"  {key}: {value}")

        # Show references if overlay or allocation
        if definition.get('type') == 'overlay':
            underlying = definition.get('underlying')
            if underlying:
                print(f"\nUnderlying Strategy: {underlying}")

        if definition.get('type') == 'allocation':
            market = definition.get('market')
            if market:
                print(f"\nMarket: {market}")

        if definition.get('type') == 'composed':
            layers = definition.get('layers', [])
            if layers:
                print(f"\nComposed Layers:")
                for i, layer in enumerate(layers, 1):
                    print(f"  {i}. {layer}")

    def get_strategy_info(self, strategy_key: str) -> Dict[str, Any]:
        """
        Get strategy information as dictionary.

        Args:
            strategy_key: Strategy identifier

        Returns:
            Dictionary with strategy details
        """
        definition = self.load_definition(strategy_key)
        return {
            'key': strategy_key,
            'type': definition.get('type'),
            'class': definition.get('class'),
            'description': definition.get('description', ''),
            'parameters': definition.get('parameters', {}),
            'market': definition.get('market'),
            'underlying': definition.get('underlying'),
            'layers': definition.get('layers', [])
        }


# Example usage and testing
if __name__ == '__main__':
    loader = StrategyLoader()

    # List all strategies
    print("Available Markets:")
    for key, desc in loader.list_strategies('market').items():
        print(f"  {key}: {desc}")

    print("\nAvailable Allocations:")
    for key, desc in loader.list_strategies('allocation').items():
        print(f"  {key}: {desc}")

    print("\nAvailable Overlays:")
    for key, desc in loader.list_strategies('overlay').items():
        print(f"  {key}: {desc}")

    print("\nAvailable Composed Strategies:")
    for key, desc in loader.list_strategies('composed').items():
        print(f"  {key}: {desc}")

    # Print info for a strategy
    print("\n" + "=" * 70)
    loader.print_strategy_info('trend_following')

    print("\n" + "=" * 70)
    loader.print_strategy_info('vol_target_12pct')

    print("\n" + "=" * 70)
    loader.print_strategy_info('trend_with_vol_12')

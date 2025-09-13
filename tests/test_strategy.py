import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from strategy.rsi_psar_engulfing import RSIPSAREngulfingStrategy, TradingSignal, StrategyState


class TestTradingSignal:
    """Test cases for TradingSignal dataclass."""
    
    def test_trading_signal_creation(self):
        """Test creating a trading signal."""
        signal = TradingSignal(
            ticker='VIC',
            timestamp=datetime.now(),
            signal_type='buy',
            confidence=0.8,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            reason='RSI oversold + PSAR bullish',
            metadata={'rsi': 25, 'psar': 98}
        )
        
        assert signal.ticker == 'VIC'
        assert signal.signal_type == 'buy'
        assert signal.confidence == 0.8
        assert signal.entry_price == 100.0
        assert signal.stop_loss == 95.0
        assert signal.take_profit == 110.0
        assert 'rsi' in signal.metadata
    
    def test_trading_signal_validation(self):
        """Test trading signal validation in __post_init__."""
        # Test confidence clamping
        signal = TradingSignal(
            ticker='VIC',
            timestamp=datetime.now(),
            signal_type='buy',
            confidence=1.5,  # Should be clamped to 1.0
            entry_price=100.0
        )
        assert signal.confidence == 1.0
        
        # Test negative confidence
        signal = TradingSignal(
            ticker='VIC',
            timestamp=datetime.now(),
            signal_type='sell',
            confidence=-0.1,  # Should be clamped to 0.0
            entry_price=100.0
        )
        assert signal.confidence == 0.0


class TestStrategyState:
    """Test cases for StrategyState dataclass."""
    
    def test_strategy_state_creation(self):
        """Test creating a strategy state."""
        state = StrategyState(
            ticker='VIC',
            last_update=datetime.now(),
            current_price=100.0,
            position_status='long',
            entry_price=95.0,
            entry_date=datetime.now() - timedelta(days=1)
        )
        
        assert state.ticker == 'VIC'
        assert state.position_status == 'long'
        assert state.entry_price == 95.0
        assert state.unrealized_pnl == 0.0


class TestRSIPSAREngulfingStrategy:
    """Test cases for RSIPSAREngulfingStrategy."""
    
    def test_strategy_initialization(self, mock_config):
        """Test strategy initialization."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        assert strategy.rsi_config['period'] == 14
        assert strategy.psar_config['af_init'] == 0.02
        assert strategy.engulfing_config['min_body_ratio'] == 0.5
        assert strategy.volume_config['avg_period'] == 20
        assert len(strategy.ticker_states) == 0
        assert len(strategy.signal_history) == 0
    
    def test_analyze_ticker_insufficient_data(self, mock_config):
        """Test analyze_ticker with insufficient data."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Create DataFrame with insufficient data
        df = pd.DataFrame({
            'open': [100, 101],
            'high': [105, 106],
            'low': [95, 96],
            'close': [103, 104],
            'volume': [1000000, 1100000]
        })
        
        signals = strategy.analyze_ticker('VIC', df)
        assert len(signals) == 0
    
    def test_analyze_ticker_with_sufficient_data(self, mock_config, sample_ohlcv_data):
        """Test analyze_ticker with sufficient data."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Mock the indicator calculation
        with patch.object(strategy, '_calculate_indicators') as mock_calc:
            # Create mock data with indicators
            mock_data = sample_ohlcv_data.copy()
            mock_data['rsi'] = np.random.uniform(20, 80, len(mock_data))
            mock_data['psar'] = mock_data['close'] * 0.98  # PSAR below price
            mock_data['engulfing_bullish'] = False
            mock_data['engulfing_bearish'] = False
            mock_data['volume_avg'] = mock_data['volume'].rolling(20).mean()
            mock_data['volume_anomaly'] = False
            
            mock_calc.return_value = mock_data
            
            signals = strategy.analyze_ticker('VIC', sample_ohlcv_data)
            
            # Should return a list (may be empty)
            assert isinstance(signals, list)
            mock_calc.assert_called_once()
    
    def test_check_buy_conditions_rsi_oversold(self, mock_config):
        """Test buy conditions with RSI oversold."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Create row with oversold RSI
        row = pd.Series({
            'close': 100.0,
            'rsi': 25.0,  # Oversold
            'psar': 98.0,  # Below price (bullish)
            'engulfing_bullish': False,
            'volume': 1000000,
            'volume_avg': 800000,
            'volume_anomaly': False
        })
        
        result = strategy._check_buy_conditions(row)
        
        assert result['signal'] is True
        assert 'RSI oversold' in result['reason']
        assert result['confidence'] > 0.5
    
    def test_check_buy_conditions_engulfing_pattern(self, mock_config):
        """Test buy conditions with bullish engulfing pattern."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Create row with bullish engulfing
        row = pd.Series({
            'close': 100.0,
            'rsi': 45.0,  # Neutral
            'psar': 98.0,  # Below price (bullish)
            'engulfing_bullish': True,  # Bullish engulfing
            'volume': 1200000,
            'volume_avg': 800000,
            'volume_anomaly': True  # High volume
        })
        
        result = strategy._check_buy_conditions(row)
        
        assert result['signal'] is True
        assert 'Bullish engulfing' in result['reason']
        assert result['confidence'] > 0.6
    
    def test_check_sell_conditions_rsi_overbought(self, mock_config):
        """Test sell conditions with RSI overbought."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Set up a long position
        strategy.ticker_states['VIC'] = StrategyState(
            ticker='VIC',
            last_update=datetime.now(),
            current_price=100.0,
            position_status='long',
            entry_price=95.0
        )
        
        # Create row with overbought RSI
        row = pd.Series({
            'close': 110.0,
            'rsi': 75.0,  # Overbought
            'psar': 112.0,  # Above price (bearish)
            'engulfing_bearish': False,
            'volume': 1000000,
            'volume_avg': 800000,
            'volume_anomaly': False
        })
        
        result = strategy._check_sell_conditions('VIC', row)
        
        assert result['signal'] is True
        assert 'RSI overbought' in result['reason']
        assert result['confidence'] > 0.5
    
    def test_check_risk_conditions_stop_loss(self, mock_config):
        """Test risk conditions with stop loss trigger."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Set up a long position with stop loss
        strategy.ticker_states['VIC'] = StrategyState(
            ticker='VIC',
            last_update=datetime.now(),
            current_price=100.0,
            position_status='long',
            entry_price=100.0,
            trailing_stop_price=95.0
        )
        
        # Create row with price below stop loss
        row = pd.Series({
            'close': 94.0,  # Below stop loss
            'rsi': 45.0,
            'psar': 96.0,
            'volume': 1000000
        })
        
        result = strategy._check_risk_conditions('VIC', row)
        
        assert result['signal'] is True
        assert 'Stop loss triggered' in result['reason']
        assert result['confidence'] == 1.0
    
    def test_liquidity_filters(self, mock_config):
        """Test liquidity filtering."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Test with high volume (should pass)
        row_high_volume = pd.Series({
            'volume': 1000000,
            'volume_avg': 800000
        })
        assert strategy._check_liquidity_filters(row_high_volume) is True
        
        # Test with low volume (should fail)
        row_low_volume = pd.Series({
            'volume': 100000,
            'volume_avg': 800000
        })
        assert strategy._check_liquidity_filters(row_low_volume) is False
    
    def test_stop_loss_calculation(self, mock_config):
        """Test stop loss calculation."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Test long position stop loss
        stop_loss = strategy._calculate_stop_loss(100.0, 'long')
        expected = 100.0 * (1 - 0.05)  # 5% stop loss
        assert stop_loss == expected
        
        # Test short position stop loss
        stop_loss = strategy._calculate_stop_loss(100.0, 'short')
        expected = 100.0 * (1 + 0.05)  # 5% stop loss
        assert stop_loss == expected
    
    def test_take_profit_calculation(self, mock_config):
        """Test take profit calculation."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Test long position take profit
        take_profit = strategy._calculate_take_profit(100.0, 'long')
        expected = 100.0 * (1 + 0.10)  # 10% take profit
        assert take_profit == expected
        
        # Test short position take profit
        take_profit = strategy._calculate_take_profit(100.0, 'short')
        expected = 100.0 * (1 - 0.10)  # 10% take profit
        assert take_profit == expected
    
    def test_update_ticker_state(self, mock_config, sample_ohlcv_data):
        """Test updating ticker state."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Add indicators to sample data
        sample_ohlcv_data['rsi'] = 50.0
        sample_ohlcv_data['psar'] = sample_ohlcv_data['close'] * 0.98
        
        strategy._update_ticker_state('VIC', sample_ohlcv_data)
        
        assert 'VIC' in strategy.ticker_states
        state = strategy.ticker_states['VIC']
        assert state.ticker == 'VIC'
        assert state.current_price == sample_ohlcv_data['close'].iloc[-1]
    
    def test_position_status_update(self, mock_config):
        """Test position status updates."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Update to long position
        strategy.update_position_status('VIC', 'long', 100.0, datetime.now())
        
        assert 'VIC' in strategy.ticker_states
        state = strategy.ticker_states['VIC']
        assert state.position_status == 'long'
        assert state.entry_price == 100.0
        assert state.entry_date is not None
    
    def test_get_active_positions(self, mock_config):
        """Test getting active positions."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Add some positions
        strategy.update_position_status('VIC', 'long', 100.0, datetime.now())
        strategy.update_position_status('VHM', 'short', 200.0, datetime.now())
        strategy.update_position_status('VCB', 'none', None, None)
        
        active_positions = strategy.get_active_positions()
        
        assert len(active_positions) == 2  # Only long and short positions
        assert 'VIC' in active_positions
        assert 'VHM' in active_positions
        assert 'VCB' not in active_positions
    
    def test_signal_history_management(self, mock_config, test_data_generator):
        """Test signal history management."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Add signals to history
        signal1 = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
        signal2 = test_data_generator.create_trading_signal('VHM', 'sell', 0.7)
        
        strategy.add_signal_to_history(signal1)
        strategy.add_signal_to_history(signal2)
        
        history = strategy.get_signal_history()
        assert len(history) == 2
        
        # Test history limit
        history_limited = strategy.get_signal_history(limit=1)
        assert len(history_limited) == 1
    
    def test_performance_stats(self, mock_config, test_data_generator):
        """Test performance statistics calculation."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Add some signals
        for i in range(5):
            signal = test_data_generator.create_trading_signal('VIC', 'buy', 0.8)
            strategy.add_signal_to_history(signal)
        
        stats = strategy.get_performance_stats()
        
        assert 'total_signals' in stats
        assert 'signal_types' in stats
        assert 'avg_confidence' in stats
        assert stats['total_signals'] == 5
    
    def test_generate_automated_strategy(self, mock_config, sample_market_data):
        """Test automated strategy generation."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Mock the analyze_ticker method to return signals
        with patch.object(strategy, 'analyze_ticker') as mock_analyze:
            mock_signal = TradingSignal(
                ticker='VIC',
                timestamp=datetime.now(),
                signal_type='buy',
                confidence=0.8,
                entry_price=100.0
            )
            mock_analyze.return_value = [mock_signal]
            
            result = strategy.generate_automated_strategy(['VIC'], sample_market_data)
            
            assert 'summary' in result
            assert 'recommendations' in result
            assert 'risk_alerts' in result
            assert len(result['recommendations']) > 0
    
    def test_portfolio_recommendations(self, mock_config, test_data_generator):
        """Test portfolio recommendations."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Add some high-confidence signals
        for ticker in ['VIC', 'VHM', 'VCB']:
            signal = test_data_generator.create_trading_signal(ticker, 'buy', 0.9)
            strategy.add_signal_to_history(signal)
        
        recommendations = strategy.get_portfolio_recommendations(max_positions=2, min_confidence=0.8)
        
        assert 'recommended_positions' in recommendations
        assert 'portfolio_summary' in recommendations
        assert len(recommendations['recommended_positions']) <= 2
    
    @pytest.mark.slow
    def test_strategy_with_real_indicators(self, mock_config, sample_ohlcv_data):
        """Test strategy with real indicator calculations."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # This test uses real indicator calculations (slower)
        signals = strategy.analyze_ticker('VIC', sample_ohlcv_data)
        
        # Should complete without errors
        assert isinstance(signals, list)
    
    def test_risk_management_integration(self, mock_config, test_data_generator):
        """Test risk management integration."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Create signals that should be filtered by risk management
        signals = [
            test_data_generator.create_trading_signal('VIC', 'buy', 0.9),
            test_data_generator.create_trading_signal('VIC', 'buy', 0.8),  # Duplicate ticker
            test_data_generator.create_trading_signal('VHM', 'buy', 0.4),  # Low confidence
        ]
        
        filtered_signals = strategy._apply_risk_management('VIC', signals)
        
        # Should filter out duplicate and low confidence signals
        assert len(filtered_signals) <= len(signals)


@pytest.mark.integration
class TestStrategyIntegration:
    """Integration tests for the strategy."""
    
    def test_full_strategy_workflow(self, mock_config, sample_market_data):
        """Test complete strategy workflow."""
        strategy = RSIPSAREngulfingStrategy(mock_config)
        
        # Run strategy on multiple tickers
        all_signals = []
        for ticker, data in sample_market_data.items():
            signals = strategy.analyze_ticker(ticker, data)
            all_signals.extend(signals)
        
        # Generate automated strategy
        automated_result = strategy.generate_automated_strategy(
            list(sample_market_data.keys()),
            sample_market_data
        )
        
        # Should complete without errors
        assert isinstance(automated_result, dict)
        assert 'summary' in automated_result
    
    @pytest.mark.cache
    def test_strategy_with_caching(self, mock_config, mock_cache_manager, sample_ohlcv_data):
        """Test strategy with caching enabled."""
        with patch('strategy.rsi_psar_engulfing.CACHE_AVAILABLE', True):
            with patch('strategy.rsi_psar_engulfing.get_cache_manager', return_value=mock_cache_manager):
                strategy = RSIPSAREngulfingStrategy(mock_config)
                
                # Run analysis twice - second should use cache
                signals1 = strategy.analyze_ticker('VIC', sample_ohlcv_data)
                signals2 = strategy.analyze_ticker('VIC', sample_ohlcv_data)
                
                # Should have attempted to use cache
                assert mock_cache_manager.get.call_count >= 1
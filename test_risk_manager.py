"""
Unit tests for the RiskManager module.
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock

from polymarket_mm_bot.utils.risk_manager import RiskManager
from polymarket_mm_bot.utils.position_manager import PositionManager, Position


@pytest.fixture
def mock_api_client():
    """Mock API client for testing"""
    return Mock()


@pytest.fixture
def position_manager(mock_api_client):
    """Create a PositionManager instance for testing"""
    return PositionManager(api_client=mock_api_client)


@pytest.fixture
def risk_manager(position_manager):
    """Create a RiskManager instance for testing"""
    return RiskManager(
        position_manager=position_manager,
        max_exposure=Decimal('1000'),
        kill_switch_threshold=Decimal('0.10'),  # 10%
        fat_finger_threshold=Decimal('0.05'),   # 5%
        starting_balance=Decimal('10000')
    )


def test_initialization(risk_manager):
    """Test RiskManager initialization"""
    assert risk_manager.max_exposure == Decimal('1000')
    assert risk_manager.kill_switch_threshold == Decimal('0.10')
    assert risk_manager.fat_finger_threshold == Decimal('0.05')
    assert risk_manager.starting_balance == Decimal('10000')


def test_calculate_total_inventory_exposure_empty(position_manager, risk_manager):
    """Test calculating exposure with no positions"""
    exposure = risk_manager.calculate_total_inventory_exposure()
    assert exposure == Decimal('0')


def test_calculate_total_inventory_exposure_with_positions(position_manager, risk_manager):
    """Test calculating exposure with positions"""
    # Add a position with YES: 600, NO: 400
    # Unhedged exposure = (600 + 400) - min(600, 400) = 1000 - 400 = 600
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('600'),
        no_balance=Decimal('400'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    exposure = risk_manager.calculate_total_inventory_exposure()
    assert exposure == Decimal('600')  # (600 + 400) - 400 = 600


def test_is_max_exposure_exceeded_false(position_manager, risk_manager):
    """Test max exposure check when not exceeded"""
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('500'),
        no_balance=Decimal('300'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    # Total exposure = (500 + 300) - 300 = 500, which is < 1000 max
    assert not risk_manager.is_max_exposure_exceeded()


def test_is_max_exposure_exceeded_true(position_manager, risk_manager):
    """Test max exposure check when exceeded"""
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('800'),
        no_balance=Decimal('500'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    # Total exposure = (800 + 500) - 500 = 800, which is < 1000 max
    # Let's add another position to exceed the limit
    position_manager.track_position(
        market_id="test_market2",
        yes_balance=Decimal('600'),
        no_balance=Decimal('500'),
        collateral_token_address="0x...",
        condition_id="test_condition2"
    )
    
    # Total exposure = 800 + (600 + 500) - 500 = 800 + 600 = 1400, which is > 1000 max
    assert risk_manager.is_max_exposure_exceeded()


def test_update_balance_and_check_kill_switch_no_trigger(risk_manager):
    """Test kill switch check when threshold not exceeded"""
    # Loss of $500 on a $10000 starting balance = 5% loss, < 10% threshold
    current_balance = Decimal('9500')
    
    should_shutdown = risk_manager.update_balance_and_check_kill_switch(current_balance)
    assert not should_shutdown


def test_update_balance_and_check_kill_switch_trigger(risk_manager):
    """Test kill switch check when threshold is exceeded"""
    # Loss of $1500 on a $10000 starting balance = 15% loss, > 10% threshold
    current_balance = Decimal('8500')
    
    should_shutdown = risk_manager.update_balance_and_check_kill_switch(current_balance)
    assert should_shutdown


def test_is_fat_finger_detected_false(risk_manager):
    """Test fat finger check when deviation is within threshold"""
    # Order at 0.50, reference at 0.51: deviation = |0.50-0.51|/0.51 = ~1.96% < 5%
    is_fat_finger = risk_manager.is_fat_finger_detected(
        market_id="test_market",
        order_price=Decimal('0.50'),
        reference_price=Decimal('0.51')
    )
    assert not is_fat_finger


def test_is_fat_finger_detected_true(risk_manager):
    """Test fat finger check when deviation exceeds threshold"""
    # Order at 0.50, reference at 0.60: deviation = |0.50-0.60|/0.60 = ~16.67% > 5%
    is_fat_finger = risk_manager.is_fat_finger_detected(
        market_id="test_market",
        order_price=Decimal('0.50'),
        reference_price=Decimal('0.60')
    )
    assert is_fat_finger


def test_get_last_known_price(risk_manager):
    """Test getting last known price from history"""
    risk_manager.update_price_history("test_market", Decimal('0.50'))
    risk_manager.update_price_history("test_market", Decimal('0.55'))
    
    last_price = risk_manager.get_last_known_price("test_market")
    assert last_price == Decimal('0.55')


def test_get_last_known_price_none(risk_manager):
    """Test getting last known price when none exists"""
    last_price = risk_manager.get_last_known_price("nonexistent_market")
    assert last_price is None


def test_check_order_risks_safe(risk_manager, position_manager):
    """Test order risk check when all checks pass"""
    # Add a position that doesn't exceed max exposure
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('400'),
        no_balance=Decimal('300'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    is_safe, violations = risk_manager.check_order_risks(
        market_id="test_market",
        order_price=Decimal('0.50'),
        reference_price=Decimal('0.51'),
        current_balance=Decimal('9500')
    )
    
    # Should be safe since exposure is 400+300-300=400 < 1000, 
    # loss is 500/10000=5% < 10%, and price deviation is 1.96% < 5%
    assert is_safe
    assert len(violations) == 0


def test_check_order_risks_violations(risk_manager, position_manager):
    """Test order risk check when violations occur"""
    # Add a position that exceeds max exposure
    position_manager.track_position(
        market_id="test_market",
        yes_balance=Decimal('800'),
        no_balance=Decimal('500'),
        collateral_token_address="0x...",
        condition_id="test_condition"
    )
    
    # Large price deviation and significant loss
    is_safe, violations = risk_manager.check_order_risks(
        market_id="test_market",
        order_price=Decimal('0.40'),
        reference_price=Decimal('0.60'),  # 33% deviation
        current_balance=Decimal('8500')   # 15% loss
    )
    
    # Should not be safe due to max exposure and kill switch and fat finger
    assert not is_safe
    assert len(violations) >= 2  # At least max exposure and kill switch should be violated


def test_should_shutdown_immediately_false(risk_manager):
    """Test shutdown check when not triggered"""
    risk_manager.hourly_loss_tracker['losses_in_period'] = Decimal('500')  # 5% loss
    risk_manager.starting_balance = Decimal('10000')
    
    assert not risk_manager.should_shutdown_immediately()


def test_should_shutdown_immediate_true(risk_manager):
    """Test shutdown check when triggered"""
    risk_manager.hourly_loss_tracker['losses_in_period'] = Decimal('1500')  # 15% loss
    risk_manager.starting_balance = Decimal('10000')

    assert risk_manager.should_shutdown_immediately()
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas.economics import IndustryPricingRequest
from app.industry.economics_service import IndustryPricingOptions


@pytest.mark.parametrize("level,expected", [(0, "0.075"), (1, "0.06675"), (5, "0.03375")])
def test_accounting_is_exact(level, expected):
    pricing = IndustryPricingRequest(accounting_level=level).to_domain()
    assert pricing.to_fee_rates().sales_tax_rate == Decimal(expected)
    assert pricing.effective_sales_tax_rate == Decimal(expected)


def test_manual_tax_remains_an_explicit_override():
    assert IndustryPricingOptions(sales_tax_basis_points=400).effective_sales_tax_rate == Decimal("0.04")
    assert IndustryPricingOptions(sales_tax_basis_points=0).effective_sales_tax_rate == 0


@pytest.mark.parametrize("level", [-1, 6, True, "5", 2.5])
def test_accounting_level_is_validated(level):
    with pytest.raises(ValidationError):
        IndustryPricingRequest(accounting_level=level)

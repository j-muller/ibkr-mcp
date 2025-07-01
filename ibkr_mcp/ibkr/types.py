from decimal import Decimal
from typing import Annotated

from ibapi.contract import Contract
from pydantic import BaseModel, Field, PlainSerializer


def serialize_contract(contract: Contract) -> dict:
    """Serialize an IBKR Contract object to a dictionary."""
    return {
        "id": contract.conId,
        "symbol": contract.symbol,
        "type": contract.secType,
        "currency": contract.currency,
        "exchange": contract.exchange,
        "primary_exchange": contract.primaryExchange,
        "last_trade_date": contract.lastTradeDateOrContractMonth,
        "strike": contract.strike,
        "right": contract.right,
        "multiplier": contract.multiplier,
    }


ContractSerializer = PlainSerializer(serialize_contract)


class Position(BaseModel, arbitrary_types_allowed=True):
    """Represents a position in the Interactive Brokers account."""

    account: Annotated[str, Field(description="Account identifier")]
    contract: Annotated[
        Contract, Field(description="Contract identifier (e.g., stock symbol)"), ContractSerializer
    ]
    position: Annotated[Decimal, Field(description="Position size")]
    average_cost: Annotated[float, Field(description="Average cost of the position (in currency)")]

    def __hash__(self):
        """Generate a unique hash for the position based on account and contract."""
        return hash((self.account, self.contract.conId))

    def __eq__(self, other):
        """Check equality of two positions based on account and contract."""
        if not isinstance(other, Position):
            return False
        return hash(self) == hash(other)

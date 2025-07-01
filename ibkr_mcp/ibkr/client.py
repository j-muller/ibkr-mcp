import asyncio
import logging
import queue
import secrets
import threading
import time
from decimal import Decimal

from ibapi import comm
from ibapi.client import EClient
from ibapi.common import MAX_MSG_LEN, NO_VALID_ID
from ibapi.contract import Contract
from ibapi.errors import BAD_LENGTH
from ibapi.ticktype import TickType, TickTypeEnum
from ibapi.wrapper import EWrapper
from pydantic import BaseModel, Field

from .types import Position

logger = logging.getLogger(__name__)


class MarketData(BaseModel):
    """Represents market data for a specific contract."""

    price: dict[str, float] = Field(default_factory=dict, description="Market data prices")
    size: dict[str, int] = Field(default_factory=dict, description="Market data sizes")


class IBKRWrapper(EWrapper):
    """Wrapper for the IBKR API client that handles market data and positions."""

    def __init__(self) -> None:
        """Initialize the IBKRWrapper."""
        super().__init__()
        self.position_event = asyncio.Event()
        self.positions: set[Position] = set()

        self.market_data_request_ids: dict[int, Contract] = {}
        self.market_data: dict[int, MarketData] = {}

    def initiate_market_data_request(self, request_id: int, contract: Contract):
        """Initiate a market data request for a given contract."""
        self.market_data_request_ids[request_id] = contract
        self.market_data[contract.conId] = MarketData()

    def tickPrice(self, reqId: int, tickType: TickType, price: float, _):  # noqa: N802, N803
        """Market data tick price callback. Handles all price related ticks."""
        contract = self._market_data_request_ids.get(reqId)
        if contract is None:
            logger.error("Market data request with ID %s not found.", reqId)
            return

        self.market_data[contract.conId].price[TickTypeEnum.idx2name[tickType]] = price

    def tickSize(self, reqId: int, tickType: TickType, size: int):  # noqa: N802, N803
        """Market data tick size callback. Handles all size-related ticks."""
        contract = self._market_data_request_ids.get(reqId)
        if not contract:
            logger.error("Market data request with ID %s not found.", reqId)
            return

        self.market_data[contract.conId].size[TickTypeEnum.idx2name[tickType]] = size

    def position(
        self,
        account: str,
        contract: Contract,
        position: Decimal,
        avgCost: float,  # noqa: N803
    ) -> None:
        """Position callback. Called when a position is received."""
        self.positions.add(
            Position(
                account=account,
                contract=contract,
                position=position,
                average_cost=avgCost,
            )
        )

    def positionEnd(self) -> None:  # noqa: N802
        """Signal that all positions have been received."""
        self.position_event.set()

    async def wait_for_positions(self) -> frozenset[Position]:
        """Wait for positions to be received."""
        for n in range(10):
            if self.position_event.is_set():
                break
            await asyncio.sleep(n / 10)
        await self.position_event.wait()
        self.position_event.clear()
        return self.positions


class IBKRClient(EClient):
    """IBKR Client that extends EClient to handle market data and positions."""

    def __init__(self):
        """Initialize the IBKR client with a custom wrapper."""
        self._wrapper = IBKRWrapper()
        super().__init__(wrapper=self._wrapper)

    def connect(self, host: str, port: int, client_id: int):
        """Connect to the IBKR API with the specified host, port, and client ID."""
        super().connect(host, port, client_id)
        threading.Thread(target=self.run).start()
        time.sleep(1)  # Wait for connection to be established

    def is_connected(self) -> bool:
        """Check if the client is connected to the IBKR API."""
        return self.isConnected()

    def run(self):
        """Run the client in a separate thread to process incoming messages."""
        while self.isConnected() or not self.msg_queue.empty():
            try:
                text = self.msg_queue.get(block=True, timeout=0.2)
            except queue.Empty:
                continue

            if len(text) > MAX_MSG_LEN:
                self.wrapper.error(
                    NO_VALID_ID, BAD_LENGTH.code(), f"{BAD_LENGTH.msg()}:{len(text)}:{text}"
                )
                break

            fields = comm.read_fields(text)
            self.decoder.interpret(fields)

        self.disconnect()

    async def get_positions(self) -> frozenset[Position]:
        """Get current positions from IBKR."""
        self.reqPositions()
        return await self._wrapper.wait_for_positions()

    async def request_market_data(self, contract: Contract):
        """Get market data for a given contract."""
        req_id = secrets.randbelow(999_999_999)

        self._wrapper.initiate_market_data_request(req_id, contract)
        self.reqMarketDataType(4)
        self.reqMktData(
            req_id, contract, "", snapshot=False, regulatorySnapshot=False, mktDataOptions=[]
        )

    def get_market_data(self, contract: Contract) -> MarketData | None:
        """Get market data for a given contract."""
        return self._wrapper.market_data.get(contract.conId)

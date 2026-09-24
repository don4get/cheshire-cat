# Investment suggestions

`/api/recommendations?portfolio=long-term&amount=1000` creates an allocation
preview from the recorded holdings in that portfolio and the latest stored
prices. It does not contact a broker or record a trade.

The default method allocates new cash toward equal weights across the known
positive-price holdings, without selling. The response includes current and
target weights, estimated quantities and values, unallocated cash, and the
reason for every suggested buy. A future strategy may supply explicit target
weights, but it must still use the known portfolio as its allowed universe.

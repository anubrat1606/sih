"""
Collusion graph service -- SIH26100.

Real graph logic over whatever bidder attributes are actually POSTed to it.
No synthetic bidders are seeded by this service -- it starts empty and only
knows about real bidders your team registers through /bidders. networkx is
used instead of standing up Neo4j for the 3-day build; the graph model
(nodes = bidders, edges = shared attribute) is identical, so porting to
Neo4j later is a data-layer swap, not a redesign.

Run: uvicorn main:app --port 8003 --reload
"""
from datetime import datetime, timezone

import networkx as nx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SIH26100 Collusion Graph Service")

# In-memory graph, keyed by tender_id -> nx.Graph. Resets if the process
# restarts -- fine for a 3-day demo, called out plainly here so nobody is
# surprised. A persistence layer (even just a JSON dump on shutdown) is a
# natural next bit if this needs to survive restarts before the demo.
graphs: dict[str, nx.Graph] = {}

SHARED_ATTRIBUTES = ["director_name", "address", "phone", "bank_account"]


class BidderIn(BaseModel):
    bidder_id: str
    tender_id: str
    director_name: str
    address: str
    phone: str
    bank_account: str


def _norm(value: str) -> str:
    return value.strip().lower()


def _get_graph(tender_id: str) -> nx.Graph:
    if tender_id not in graphs:
        graphs[tender_id] = nx.Graph()
    return graphs[tender_id]


@app.post("/bidders")
async def add_bidder(bidder: BidderIn):
    g = _get_graph(bidder.tender_id)

    attrs = {
        "director_name": _norm(bidder.director_name),
        "address": _norm(bidder.address),
        "phone": _norm(bidder.phone),
        "bank_account": _norm(bidder.bank_account),
    }

    g.add_node(bidder.bidder_id, **attrs, raw={
        "director_name": bidder.director_name,
        "address": bidder.address,
        "phone": bidder.phone,
        "bank_account": bidder.bank_account,
    })

    new_edges = []
    for other_id, other_attrs in list(g.nodes(data=True)):
        if other_id == bidder.bidder_id:
            continue
        for field in SHARED_ATTRIBUTES:
            if attrs[field] and attrs[field] == other_attrs.get(field):
                g.add_edge(bidder.bidder_id, other_id, shared_attribute=field, value=attrs[field])
                new_edges.append({"with": other_id, "on": field})

    return {"bidder_id": bidder.bidder_id, "tender_id": bidder.tender_id, "new_edges": new_edges}


@app.get("/collusion/{bidder_id}")
async def get_collusion(bidder_id: str, tender_id: str):
    g = _get_graph(tender_id)
    if bidder_id not in g:
        raise HTTPException(status_code=404, detail=f"bidder_id {bidder_id} not found in tender {tender_id}")

    degree = g.degree(bidder_id)
    flagged = degree >= 1

    cluster_id = None
    shared_with = []
    if flagged:
        component = nx.node_connected_component(g, bidder_id)
        cluster_id = "cluster_" + "_".join(sorted(component))
        for neighbor in g.neighbors(bidder_id):
            edge_data = g.get_edge_data(bidder_id, neighbor)
            shared_with.append({
                "bidder_id": neighbor,
                "shared_attribute": edge_data["shared_attribute"],
                "value": edge_data["value"],
            })

    return {
        "bidder_id": bidder_id,
        "tender_id": tender_id,
        "flagged": flagged,
        "cluster_id": cluster_id,
        "shared_with": shared_with,
    }


@app.get("/graph/{tender_id}")
async def get_graph(tender_id: str):
    g = _get_graph(tender_id)
    nodes = list(g.nodes())
    edges = [
        {"from": u, "to": v, "shared_attribute": d["shared_attribute"]}
        for u, v, d in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

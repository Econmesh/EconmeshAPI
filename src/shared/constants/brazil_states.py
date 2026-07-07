"""Brazilian state (UF) adjacency map for location matching."""

from __future__ import annotations

STATE_NEIGHBORS: dict[str, frozenset[str]] = {
    "AC": frozenset({"AM", "RO"}),
    "AL": frozenset({"PE", "BA", "SE"}),
    "AM": frozenset({"RR", "PA", "MT", "RO", "AC"}),
    "AP": frozenset({"PA"}),
    "BA": frozenset({"SE", "AL", "PE", "PI", "TO", "GO", "MG", "ES"}),
    "CE": frozenset({"RN", "PB", "PE", "PI"}),
    "DF": frozenset({"GO"}),
    "ES": frozenset({"BA", "MG", "RJ"}),
    "GO": frozenset({"DF", "MG", "MS", "MT", "TO", "BA"}),
    "MA": frozenset({"PI", "TO", "PA"}),
    "MG": frozenset({"ES", "RJ", "SP", "MS", "GO", "BA"}),
    "MS": frozenset({"SP", "PR", "MG", "GO", "MT"}),
    "MT": frozenset({"RO", "AM", "PA", "TO", "GO", "MS"}),
    "PA": frozenset({"AP", "AM", "RR", "MA", "TO"}),
    "PB": frozenset({"RN", "CE", "PE"}),
    "PE": frozenset({"PB", "CE", "PI", "BA", "AL"}),
    "PI": frozenset({"MA", "CE", "PE", "BA", "TO"}),
    "PR": frozenset({"SP", "MS", "SC"}),
    "RJ": frozenset({"SP", "MG", "ES"}),
    "RN": frozenset({"CE", "PB"}),
    "RO": frozenset({"AC", "AM", "MT"}),
    "RR": frozenset({"PA", "AM"}),
    "RS": frozenset({"SC"}),
    "SC": frozenset({"PR", "RS"}),
    "SE": frozenset({"BA", "AL"}),
    "SP": frozenset({"MG", "RJ", "PR", "MS"}),
    "TO": frozenset({"PA", "MA", "PI", "BA", "GO", "MT"}),
}


def are_neighboring_states(state_a: str, state_b: str) -> bool:
    """Return True when two UF codes share a border."""
    a = state_a.upper().strip()
    b = state_b.upper().strip()
    if a == b:
        return False
    return b in STATE_NEIGHBORS.get(a, frozenset())


__all__ = ["STATE_NEIGHBORS", "are_neighboring_states"]

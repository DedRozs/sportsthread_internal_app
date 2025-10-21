from typing import Any, Dict, List, Tuple
from .spec_constants import ROLE_ATHLETE, ROLE_COACH

def _jersey_key(val: str | None) -> Tuple[int, str]:
    if val is None:
        return (10**9, "")  # blanks last
    s = str(val).strip()
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            break
    if num == "":
        return (10**9, s)
    return (int(num), s)

def group_and_sort(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Group by Team_ID; split athletes vs coaches; pick lowest-id coach
    teams: Dict[str, Any] = {}
    for r in rows:
        tid = str(r["Team_ID"])
        t = teams.setdefault(tid, {"meta": {}, "athletes": [], "coach": None})
        if not t["meta"]:
            t["meta"] = {
                "Event_Name": r.get("Event_Name"),
                "Team_Name": r["Team_Name"],
                "Team_ID": r["Team_ID"],
                "Division": r.get("Division"),
            }
        if r.get("Usertype_ID") == ROLE_ATHLETE:
            t["athletes"].append(r)
        elif r.get("Usertype_ID") == ROLE_COACH:
            c = t["coach"]
            if c is None or int(r["User_ID"]) < int(c["User_ID"]):
                t["coach"] = r

    # Sort athletes: Jersey_Num numeric asc; blanks last; tie by Name
    for t in teams.values():
        t["athletes"].sort(key=lambda r: (_jersey_key(r.get("Jersey_Num")), r.get("Name","")))
    return teams

__all__ = ["group_and_sort"]
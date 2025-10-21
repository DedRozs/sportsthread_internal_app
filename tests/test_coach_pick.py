from app.roster.sort_and_group import group_and_sort
def test_lowest_user_id_coach_is_picked():
    rows = [
        {"Team_Name":"Y","Team_ID":2,"Usertype_ID":2,"User_ID":99,"Name":"Coach B"},
        {"Team_Name":"Y","Team_ID":2,"Usertype_ID":2,"User_ID":10,"Name":"Coach A"},
        {"Team_Name":"Y","Team_ID":2,"Usertype_ID":1,"User_ID":1,"Name":"P","Jersey_Num":"1"},
    ]
    t = next(iter(group_and_sort(rows).values()))
    assert t["coach"]["Name"] == "Coach A"

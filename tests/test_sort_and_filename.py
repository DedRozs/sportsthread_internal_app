from app.roster.sort_and_group import group_and_sort
from app.roster.sanitize import pdf_filename

def test_sorting_blank_last_and_tie_by_name():
    rows = [
        {"Team_Name":"X","Team_ID":1,"Usertype_ID":1,"User_ID":3,"Name":"Zed","Jersey_Num":"12"},
        {"Team_Name":"X","Team_ID":1,"Usertype_ID":1,"User_ID":4,"Name":"Amy","Jersey_Num":"12"},
        {"Team_Name":"X","Team_ID":1,"Usertype_ID":1,"User_ID":2,"Name":"Bob","Jersey_Num":""},
        {"Team_Name":"X","Team_ID":1,"Usertype_ID":1,"User_ID":1,"Name":"Cat","Jersey_Num":"3"},
    ]
    teams = group_and_sort(rows)
    athletes = next(iter(teams.values()))["athletes"]
    assert [a["Name"] for a in athletes] == ["Cat","Amy","Zed","Bob"]

def test_filename_sanitization_examples():
    assert pdf_filename("Tigers 14U", 8735) == "Tigers_14U_8735.pdf"
    assert pdf_filename("ACME Elite – Blue", 42) == "ACME_Elite_Blue_42.pdf"

# Canonical columns and roles per the roster spec.
# Keep names and order EXACTLY as in the SQL/result set.
COLUMNS = [
    "Event_ID", "Event_Name", "Team_Name", "Team_ID", "Division", "User_ID",
    "Name", "Usertype_ID", "Phone", "Email", "Profile_Pic", "Jersey_Num", "Birthday",
]
ROLE_ATHLETE = 1
ROLE_COACH = 2
__all__ = ["COLUMNS", "ROLE_ATHLETE", "ROLE_COACH"]
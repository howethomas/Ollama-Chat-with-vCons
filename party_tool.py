PARTY_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_party",
        "description": "Returns the vCons for the named party. Supports identification of matching converstaions by tel, mailto, and name.",
        "parameters": {
            "type": "object",
            "properties": {
                "party": {
                    "type": "string",
                    "description": "The party to find. Supports tel, mailto, and name."
                }
            },
            "required": ["party"]
        }
    }
} 

def find_by_party(party, conn):
	
   # Strip the tel, mailto, or name from the party string
	party = party.replace("tel:", "").replace("mailto:", "").replace("name:", "")

	# Take a brute force approach to parsing the party string
	query = """
		SELECT * FROM vcon WHERE uuid IN (
			SELECT vcon_uuid FROM party WHERE mailto = %s or tel = %s or name = %s
		)
	"""

	cursor = conn.cursor()
	cursor.execute(query, (party, party, party))
	results = cursor.fetchall()
	cursor.close()

	return results
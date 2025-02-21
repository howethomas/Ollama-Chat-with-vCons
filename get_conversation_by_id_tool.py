GET_CONVERSATION_BY_ID = {
    "type": "function",
    "function": {
        "name": "get_conversation_by_id",
        "description": "Returns the vCons with the matching uuid.",
        "parameters": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "The uuid of the vCon to get."
                }
            },
            "required": ["uuid"]
        }
    }
} 

def get_conversation_by_id(uuid, conn):
	
	# Take a brute force approach to parsing the party string
	query = """
		SELECT * FROM vcon WHERE uuid = %s
	"""

	cursor = conn.cursor()
	cursor.execute(query, (uuid,))
	results = cursor.fetchall()
	cursor.close()

	return results
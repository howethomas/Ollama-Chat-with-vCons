DATE_RANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "find_by_date_range",
        "description": "Returns the vCons where the created_at date is between the start and end dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "The start date of the range, ISO 8601 format."
                },
                "end_date": {
                    "type": "string",
                    "description": "The end date of the range, ISO 8601 format."
                }
            },
            "required": ["start_date", "end_date"]
        }
    }
} 

def find_by_date_range(start_date, end_date, conn):
	
	# Take a brute force approach to parsing the party string
	query = """
		SELECT * FROM vcon WHERE created_at BETWEEN %s AND %s
	"""

	cursor = conn.cursor()
	cursor.execute(query, (start_date, end_date))
	results = cursor.fetchall()
	cursor.close()

	return results
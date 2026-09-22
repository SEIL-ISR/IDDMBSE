using HTTP



############################################################################################
# Define the endpoint URL
url = "your_webapp_url"

# Make a GET request to the endpoint
response = HTTP.get(url)

# Check if the request was successful
if response.status == 200
    # Extract the data from the response
    data = JSON.parse(response.body)

    # Print the data
    println(data)
else
    # Print an error message
    println("Error retrieving data: ", response.status)
end
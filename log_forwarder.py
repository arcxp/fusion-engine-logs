import boto3  # AWS SDK for Python to interact with AWS services
import gzip  # Module for compressing and decompressing data
import json  # Module for working with JSON data
import os  # Module for interacting with the operating system
import base64  # Module for encoding and decoding data in base64
import time  # Module for time-related functions

# Initialize AWS clients for Kinesis, CloudWatch Logs, and S3
kinesis_client = boto3.client("kinesis")
logs_client = boto3.client("logs")
s3_client = boto3.client("s3")

# Configuration variables loaded from environment variables
s3_bucket_name = os.getenv("S3_BUCKET_NAME", "arcxpplogs-<MyOrganizationName>")  # S3 bucket name where the logs will be stored
log_group_name = "ArcXP/DynamicLogStreams"  # CloudWatch Logs group name
stream_tokens = {}  # Dictionary to store sequence tokens for log streams
max_log_buffer_size = 100  # Maximum number of log messages to buffer before uploading to S3

def ensure_log_group():
    """Ensure that the CloudWatch Logs group exists."""
    try:
        logs_client.create_log_group(logGroupName=log_group_name)  # Create log group
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass  # If the log group already exists, do nothing

def ensure_log_stream(log_stream_name):
    """Ensure that the specified log stream exists within the log group."""
    if log_stream_name not in stream_tokens:
        try:
            # Create a new log stream
            logs_client.create_log_stream(
                logGroupName=log_group_name,
                logStreamName=log_stream_name
            )
            stream_tokens[log_stream_name] = None  # Initialize token for the new stream
        except logs_client.exceptions.ResourceAlreadyExistsException:
            # If the log stream already exists, retrieve its sequence token
            response = logs_client.describe_log_streams(
                logGroupName=log_group_name,
                logStreamNamePrefix=log_stream_name
            )
            if response["logStreams"]:
                token = response["logStreams"][0].get("uploadSequenceToken")
                stream_tokens[log_stream_name] = token

def send_to_cloudwatch_log(message, timestamp, log_stream_name):
    """Send a log message to CloudWatch Logs."""
    ensure_log_stream(log_stream_name)  # Ensure the log stream exists
    token = stream_tokens.get(log_stream_name)  # Get the sequence token for the log stream

    # Prepare the log event
    log_event = {
        'logGroupName': log_group_name,
        'logStreamName': log_stream_name,
        'logEvents': [{'timestamp': timestamp, 'message': message}]
    }
    if token:
        log_event['sequenceToken'] = token  # Include the sequence token if available

    # Send the log event to CloudWatch Logs
    response = logs_client.put_log_events(**log_event)
    stream_tokens[log_stream_name] = response['nextSequenceToken']  # Update the sequence token

def upload_to_s3(log_buffer, log_stream_name):
    """Upload buffered log messages to S3."""
    if not log_buffer:
        return  # If the buffer is empty, do nothing

    # Create the S3 key using the log stream name and current date
    s3_key = f"{log_stream_name}/{time.strftime('%Y-%m-%d')}.log"
    log_data = "\n".join(log_buffer)  # Join the log messages into a single string

    # Upload the log data to S3
    s3_client.put_object(
        Bucket=s3_bucket_name,
        Key=s3_key,
        Body=log_data
    )

def handler(event, context):
    """
    AWS Lambda function to process log records from Kinesis, forward them to CloudWatch Logs, 
    and upload them to S3.

    Parameters:
    - event: dict, required
        The event parameter contains the data passed to the function upon invocation. 
        It includes records from the Kinesis stream.

    - context: object, required
        The context parameter provides methods and properties that provide information 
        about the invocation, function, and execution environment.

    Returns:
    - dict
        A dictionary with a statusCode and body indicating the result of the processing.
    """
    ensure_log_group()  # Ensure the log group exists
    log_buffer = []  # Initialize a buffer to store log messages

    for record in event['Records']:
        try:
            # Decode the base64-encoded data from Kinesis
            compressed_payload = base64.b64decode(record['kinesis']['data'])
            # Decompress the gzipped data
            decompressed = gzip.decompress(compressed_payload)
            # Parse the JSON payload
            payload = json.loads(decompressed)

            # Determine the log stream name, replacing slashes with underscores
            log_stream_name = payload.get("logGroup", "unknown-source").replace("/", "_")

            for event_log in payload.get("logEvents", []):
                message = event_log.get("message", "")  # Extract the log message
                timestamp = int(event_log.get("timestamp", time.time() * 1000))  # Extract the timestamp

                # Print the log message for debugging
                print(f"[{log_stream_name}] Forwarding: {message.strip()}")
                # Send the log message to CloudWatch Logs
                send_to_cloudwatch_log(message.strip(), timestamp, log_stream_name)
                # Add the log message to the buffer
                log_buffer.append(message.strip())

                # If the buffer reaches the maximum size, upload it to S3
                if len(log_buffer) >= max_log_buffer_size:
                    upload_to_s3(log_buffer, log_stream_name)
                    log_buffer.clear()  # Clear the buffer after uploading

        except Exception as e:
            print("Error processing record:", e)  # Print any errors encountered

    if log_buffer:
        upload_to_s3(log_buffer, log_stream_name)  # Upload any remaining log messages

    return {
        'statusCode': 200,
        'body': 'Processed records and forwarded to CloudWatch Logs + S3.'
    }

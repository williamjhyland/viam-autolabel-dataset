import asyncio
import io
import os
import viam
from PIL import Image, ImageDraw
from viam.services.vision import VisionClient
from viam.robot.client import RobotClient
from viam.media.utils.pil import viam_to_pil_image, pil_to_viam_image, CameraMimeType
from viam.app.viam_client import ViamClient, DataClient
from viam.rpc.dial import DialOptions
from viam.proto.app.data import BinaryID
from viam.utils import create_filter
from io import BytesIO
import json
import time

# Connect to Viam
async def viam_connect(api_key, api_key_id) -> ViamClient:
    dial_options = DialOptions.with_api_key( 
        api_key=api_key,
        api_key_id=api_key_id
    )
    return await ViamClient.create_from_dial_options(dial_options)

# Connect to Robot Running Vision Service
async def robot_connect(api_key, api_key_id) -> RobotClient:
    opts = RobotClient.Options.with_api_key( 
        api_key=api_key,
        api_key_id=api_key_id
    )
    return await RobotClient.at_address('mylaptop-main.0p1kevpomd.viam.cloud', opts)

# Load Configuration File
def load_configuration(file_path):
    with open(file_path, 'r') as file:
        config = json.load(file)
    return config

# Upload Images to Viam Data Set
async def autoLabelDataset(viamClient: ViamClient, robotClient: RobotClient, dataset_id: str):
    data_client: DataClient = viamClient.data_client
    my_data = []
    last = None
    # NOTE: I want to filter for all none labeled images (or images not labeled "auto-label")
    # TODO: Figure out if this can be done
    my_filter = create_filter(
        dataset_id=dataset_id,
        tags=None
        )
    print("Starting loop...")
    while True:
        # Get the data from Viam
        # NOTE: This is incurring download costs...
        # TODO: Clarify if this is a dumb way to get the data.

        data, count, last = await data_client.binary_data_by_filter(filter=my_filter, last=last, include_binary_data=True, limit=1)
        if not data:
            print(data)
            break

        print("Got image...")
        
        # Create an Image
        image = Image.open(BytesIO(data[0].binary))
        # Turn that into a "Viam Image"
        viamImage = pil_to_viam_image(image.convert('RGB'), CameraMimeType.JPEG)

        # If the data is not already labeled
        if "auto-labeled" not in data[0].metadata.capture_metadata.tags:
            print("Image not auto-labeled")
            # RECREATE the BinaryID???
            binaryID = BinaryID(
                file_id=data[0].metadata.id,
                organization_id='0b5b5b7c-d61a-4984-b294-6d73a9076adb',
                location_id='0p1kevpomd'
            )
            
            # Get visionServices from Robot
            print("Running florence")
            objectDetection = VisionClient.from_robot(robotClient, "myFlorenceVision")
            print("Running ChatGPT")
            objectClassifier = VisionClient.from_robot(robotClient, "myChatGPTVision")
            scoreThreshold = 0.3
            validLabels = ['food']

            # Get detections from the vision service
            detections = await objectDetection.get_detections(image=viamImage)
            print("Florence Detections: ", detections)

            # First filter: Filter detections based on confidence score
            filtered_score_detections = [detection for detection in detections if detection.confidence > scoreThreshold]

            # Second filter: Further filter detections based on valid labels
            filtered_detections = [detection for detection in filtered_score_detections if detection.class_name in validLabels]

            # Assuming image.size gives (width, height)
            image_width, image_height = image.size

            # Draw bounding boxes
            for detection in filtered_detections:
                # Crop the image based on the bounding box coordinates
                cropped_image = image.crop((detection.x_min, detection.y_min, detection.x_max, detection.y_max))

                # Convert the cropped image to the Viam image format
                cropped_viam_image = pil_to_viam_image(cropped_image.convert('RGB'), CameraMimeType.JPEG)

                # Get the ChatGPT defined label
                labels = await objectClassifier.get_classifications(image=cropped_viam_image, count=1, extra={"question": "Here is a list of 20 ingredients: Udon, Broccoli, Carrots, Mushrooms, Lo Mein, Cabbage, Rice Noodles, Penne, Cavatappi, Red Onion, Tortelloni, Roasted Zucchini, Grilled Chicken, Shrimp, Steak, Meatballs, Tofu, Spaghetti, Zoodles, Tomatoes. Passing only the ingredients back as an answer. Which of these ingredients are in this image?"})
                label = labels[0].class_name
                print(labels, label)

                # Normalize the bounding box coordinates
                x_min_normalized = detection.x_min / image_width
                y_min_normalized = detection.y_min / image_height
                x_max_normalized = detection.x_max / image_width
                y_max_normalized = detection.y_max / image_height

                # Add Bounding Box
                await data_client.add_bounding_box_to_image_by_id(binary_id=binaryID, label=label, x_min_normalized=x_min_normalized, y_min_normalized=y_min_normalized, x_max_normalized=x_max_normalized, y_max_normalized=y_max_normalized)
                # Add "Auto-Labeled" Tag
                await data_client.add_tags_to_binary_data_by_ids(tags=["auto-labeled"], binary_ids=[binaryID])

    pass

async def main():
    # Define the path to the configuration file
    config_file_path = 'configuration.json'
    
    # Load the configuration
    config = load_configuration(config_file_path)

    # Initialize variables
    dataset_id = config.get("dataset_id", "")
    api_key = config.get("app_api_key", "")
    api_key_id = config.get("app_api_key_id", "")

    # Connect to Viam
    viam_client: ViamClient = await viam_connect(api_key, api_key_id)

    # Connect to Robot
    robot_client: RobotClient = await robot_connect(api_key, api_key_id)

    # Iterate over all images in the dataset
    print("Labeling data start")
    await autoLabelDataset(viam_client, robot_client, dataset_id)
    # Move all the images with the binary IDs to the appropriate data set
    print("Labeling data complete")
    viam_client.close()

if __name__ == "__main__":
    asyncio.run(main())

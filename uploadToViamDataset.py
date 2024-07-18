import asyncio
import io
import os
from PIL import Image
from viam.media.utils.pil import viam_to_pil_image, pil_to_viam_image, CameraMimeType
from viam.app.viam_client import ViamClient
from viam.rpc.dial import DialOptions
from viam.proto.app.data import BinaryID
import json

# Connect to Viam
async def viam_connect(api_key, api_key_id) -> ViamClient:
    dial_options = DialOptions.with_api_key( 
        api_key=api_key,
        api_key_id=api_key_id
    )
    return await ViamClient.create_from_dial_options(dial_options)

# Load Configuration File
def load_configuration(file_path):
    with open(file_path, 'r') as file:
        config = json.load(file)
    return config

# Upload Images to Viam Data Set
async def upload_image(app_client: ViamClient, image_path: str, part_id: str, org_id: str, location_id: str, upload_tag: str):
    with Image.open(image_path) as im:
        if im.mode == 'RGBA':
            im = im.convert('RGB')
        buf = io.BytesIO()
        im.save(buf, format='JPEG')
        # Upload Image to Viam
        img_id = await app_client.data_client.file_upload(part_id=part_id, file_extension=".jpg", data=buf.getvalue())
        # Create the Binary ID
        binary_id = BinaryID(
            file_id=img_id,
            organization_id=org_id,
            location_id=location_id
        )
        await app_client.data_client.add_tags_to_binary_data_by_ids(tags=[upload_tag], binary_ids=[binary_id])
    return binary_id

async def main():
    # Define the path to the configuration file
    config_file_path = 'configuration.json'
    
    # Load the configuration
    config = load_configuration(config_file_path)

    # Initialize variables
    dataset_id = config.get("dataset_id", "")
    api_key = config.get("app_api_key", "")
    api_key_id = config.get("app_api_key_id", "")
    part_id = config.get("part_id", "")
    org_id = config.get("org_id", "")
    location_id = config.get("location_id", "")
    image_directory = config.get("image_directory", "")
    upload_tag = config.get("upload_tags", "")

    # Connect to Viam
    app_client: ViamClient = await viam_connect(api_key, api_key_id)
    print(app_client)

    # Iterate over all images in the directory
    binary_ids = []
    for filename in os.listdir(image_directory):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            # Get the Image Path
            image_path = os.path.join(image_directory, filename)
            # Upload the Images
            binary_id = await upload_image(app_client, image_path, part_id, org_id, location_id, upload_tag)
            # Add the Binary ID of the Image to a list
            binary_ids.append(binary_id)
    print(binary_ids)
    # Move all the images with the binary IDs to the appropriate data set
    result = await app_client.data_client.add_binary_data_to_dataset_by_ids(binary_ids=binary_ids, dataset_id=dataset_id)
    app_client.close()

if __name__ == "__main__":
    asyncio.run(main())

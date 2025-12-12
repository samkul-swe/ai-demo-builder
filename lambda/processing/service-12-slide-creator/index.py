"""
Service 12: Slide Creator
Creates PNG transition slides with text using PIL/Pillow
Automatically generates slides from session data

CORRECTED VERSION - Auto-generates slides from session suggestions
"""

import os
import json
import boto3
from datetime import datetime
import tempfile
import shutil
from PIL import Image, ImageDraw, ImageFont
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
TABLE_NAME = os.environ.get('SESSIONS_TABLE')
STITCHER_FUNCTION = os.environ.get('STITCHER_FUNCTION_NAME', 'service-13-video-stitcher')

# Slide dimensions
SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

# Color schemes for different slide types
COLOR_SCHEMES = {
    'title': {
        'bg_color': (26, 26, 46),       # Dark blue
        'title_color': (255, 255, 255),
        'subtitle_color': (160, 160, 160),
        'accent_color': (79, 70, 229)
    },
    'section': {
        'bg_color': (15, 23, 42),
        'title_color': (255, 255, 255),
        'subtitle_color': (203, 213, 225),
        'accent_color': (59, 130, 246)
    },
    'end': {
        'bg_color': (30, 27, 75),
        'title_color': (255, 255, 255),
        'subtitle_color': (196, 181, 253),
        'accent_color': (139, 92, 246)
    }
}


def get_font(size):
    """Get a font, falling back to default if custom fonts unavailable"""
    font_paths = [
        '/usr/share/fonts/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/var/task/fonts/DejaVuSans.ttf',
        '/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    
    # Fall back to default font
    try:
        return ImageFont.load_default()
    except:
        return None


def get_text_size(draw, text, font):
    """Get text bounding box size"""
    if font:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return len(text) * 10, 20


def draw_centered_text(draw, text, y_position, font, color, width=SLIDE_WIDTH):
    """Draw text centered horizontally at given y position"""
    if not text:
        return
    
    text_width, text_height = get_text_size(draw, text, font)
    x = (width - text_width) // 2
    draw.text((x, y_position), text, font=font, fill=color)


def create_title_slide(project_name, owner):
    """Create opening title slide"""
    scheme = COLOR_SCHEMES['title']
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), scheme['bg_color'])
    draw = ImageDraw.Draw(img)
    
    # Fonts
    title_font = get_font(96)
    subtitle_font = get_font(48)
    
    center_y = SLIDE_HEIGHT // 2
    
    # Draw project name
    draw_centered_text(draw, project_name, center_y - 100, title_font, scheme['title_color'])
    
    # Draw subtitle
    subtitle = f"by {owner}"
    draw_centered_text(draw, subtitle, center_y + 20, subtitle_font, scheme['subtitle_color'])
    
    # Draw "Demo Video" text
    demo_font = get_font(32)
    draw_centered_text(draw, "Demo Video", SLIDE_HEIGHT - 120, demo_font, scheme['accent_color'])
    
    # Add decorative line
    line_y = center_y - 10
    line_width = 200
    line_x = (SLIDE_WIDTH - line_width) // 2
    draw.rectangle([line_x, line_y, line_x + line_width, line_y + 4], fill=scheme['accent_color'])
    
    return img


def create_section_slide(sequence_number, title, duration):
    """Create section transition slide"""
    scheme = COLOR_SCHEMES['section']
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), scheme['bg_color'])
    draw = ImageDraw.Draw(img)
    
    # Fonts
    num_font = get_font(36)
    title_font = get_font(72)
    duration_font = get_font(32)
    
    center_y = SLIDE_HEIGHT // 2
    
    # Draw section number
    section_label = f"Part {sequence_number}"
    draw_centered_text(draw, section_label, center_y - 140, num_font, scheme['accent_color'])
    
    # Draw section title (wrap long titles)
    if len(title) > 40:
        # Split into two lines
        words = title.split()
        mid = len(words) // 2
        line1 = ' '.join(words[:mid])
        line2 = ' '.join(words[mid:])
        draw_centered_text(draw, line1, center_y - 60, title_font, scheme['title_color'])
        draw_centered_text(draw, line2, center_y + 20, title_font, scheme['title_color'])
    else:
        draw_centered_text(draw, title, center_y - 40, title_font, scheme['title_color'])
    
    # Draw duration
    duration_text = f"Duration: {duration}"
    draw_centered_text(draw, duration_text, center_y + 100, duration_font, scheme['subtitle_color'])
    
    # Add decorative bars
    draw.rectangle([100, center_y - 50, 108, center_y + 50], fill=scheme['accent_color'])
    draw.rectangle([SLIDE_WIDTH - 108, center_y - 50, SLIDE_WIDTH - 100, center_y + 50], fill=scheme['accent_color'])
    
    return img


def create_end_slide(project_name):
    """Create closing/thank you slide"""
    scheme = COLOR_SCHEMES['end']
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT), scheme['bg_color'])
    draw = ImageDraw.Draw(img)
    
    # Fonts
    title_font = get_font(96)
    subtitle_font = get_font(42)
    
    center_y = SLIDE_HEIGHT // 2
    
    # Draw title
    draw_centered_text(draw, "Thank You!", center_y - 60, title_font, scheme['title_color'])
    
    # Draw subtitle
    subtitle = f"Check out {project_name} on GitHub"
    draw_centered_text(draw, subtitle, center_y + 50, subtitle_font, scheme['subtitle_color'])
    
    return img


def generate_slides_from_session(session_id):
    """
    Automatically generate slides based on session data
    
    Creates:
    - 1 title slide (opening)
    - N section slides (one per video suggestion)
    - 1 end slide (closing)
    
    Returns:
        list: Generated slide information
    """
    # Get session from DynamoDB
    table = dynamodb.Table(TABLE_NAME)
    response = table.get_item(Key={'id': session_id})
    
    if 'Item' not in response:
        raise ValueError(f"Session '{session_id}' not found")
    
    session = response['Item']
    
    project_name = session.get('project_name', 'Unknown Project')
    owner = session.get('owner', 'unknown')
    suggestions = session.get('suggestions', [])
    
    if not suggestions:
        raise ValueError("No suggestions found in session")
    
    logger.info(f"[Service12] Generating slides for: {project_name}")
    logger.info(f"[Service12] Total suggestions: {len(suggestions)}")
    
    # Create temp directory
    work_dir = tempfile.mkdtemp()
    generated_slides = []
    
    try:
        # 1. Create title slide
        logger.info(f"[Service12] Creating title slide...")
        title_img = create_title_slide(project_name, owner)
        title_path = os.path.join(work_dir, 'slide_title.png')
        title_img.save(title_path, 'PNG', quality=95)
        
        title_s3_key = f'slides/{session_id}/slide_title.png'
        upload_to_s3(title_path, title_s3_key)
        
        generated_slides.append({
            'id': 'title',
            'type': 'title',
            's3_key': title_s3_key,
            'order': 0
        })
        
        # 2. Create section slides (one per video suggestion)
        for idx, suggestion in enumerate(suggestions):
            sequence_num = suggestion.get('sequence_number', idx + 1)
            title = suggestion.get('title', f'Section {sequence_num}')
            duration = suggestion.get('duration', 'N/A')
            
            logger.info(f"[Service12] Creating section slide {sequence_num}: {title}")
            
            section_img = create_section_slide(sequence_num, title, duration)
            section_path = os.path.join(work_dir, f'slide_section_{sequence_num}.png')
            section_img.save(section_path, 'PNG', quality=95)
            
            section_s3_key = f'slides/{session_id}/slide_section_{sequence_num}.png'
            upload_to_s3(section_path, section_s3_key)
            
            generated_slides.append({
                'id': f'section_{sequence_num}',
                'type': 'section',
                's3_key': section_s3_key,
                'order': sequence_num,
                'video_sequence': sequence_num  # Links to video
            })
        
        # 3. Create end slide
        logger.info(f"[Service12] Creating end slide...")
        end_img = create_end_slide(project_name)
        end_path = os.path.join(work_dir, 'slide_end.png')
        end_img.save(end_path, 'PNG', quality=95)
        
        end_s3_key = f'slides/{session_id}/slide_end.png'
        upload_to_s3(end_path, end_s3_key)
        
        generated_slides.append({
            'id': 'end',
            'type': 'end',
            's3_key': end_s3_key,
            'order': len(suggestions) + 1
        })
        
        logger.info(f"[Service12] ✅ Generated {len(generated_slides)} slides")
        
        # Update DynamoDB with slide information
        table.update_item(
            Key={'id': session_id},
            UpdateExpression='SET slides = :slides, slides_count = :count, #status = :status, updated_at = :now',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':slides': generated_slides,
                ':count': len(generated_slides),
                ':status': 'slides_ready',
                ':now': datetime.utcnow().isoformat() + 'Z'
            }
        )
        
        logger.info(f"[Service12] ✅ Updated DynamoDB with slide information")
        
        # Trigger Service 13 (Video Stitcher) asynchronously
        trigger_video_stitcher(session_id, generated_slides)
        
        return generated_slides
        
    finally:
        # Cleanup temp directory
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
            logger.info(f"[Service12] Cleaned up temp directory")


def trigger_video_stitcher(session_id, slides):
    """
    Trigger Service 13 (Video Stitcher) asynchronously
    """
    try:
        payload = {
            'session_id': session_id,
            'slides': slides
        }
        
        logger.info(f"[Service12] Triggering video stitcher: {STITCHER_FUNCTION}")
        
        lambda_client.invoke(
            FunctionName=STITCHER_FUNCTION,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps(payload)
        )
        
        logger.info(f"[Service12] ✅ Triggered Service 13 (Video Stitcher)")
        
    except Exception as e:
        logger.error(f"[Service12] ⚠️ Failed to trigger stitcher (non-critical): {e}")


def lambda_handler(event, context):
    """
    Service 12: Slide Creator
    Generates transition slides for demo video
    
    Can be triggered by:
    1. SQS event (from Service 11)
    2. Direct API call
    """
    logger.info(f"[Service12] Event: {json.dumps(event)}")
    
    try:
        # Handle SQS trigger (from Service 11)
        if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:sqs':
            logger.info("[Service12] Processing SQS trigger")
            
            results = []
            for record in event['Records']:
                message = json.loads(record['body'])
                session_id = message.get('session_id')
                
                if not session_id:
                    logger.error("[Service12] No session_id in SQS message")
                    continue
                
                logger.info(f"[Service12] Processing session: {session_id}")
                
                # Generate slides
                slides = generate_slides_from_session(session_id)
                
                results.append({
                    'session_id': session_id,
                    'slides_count': len(slides),
                    'status': 'success'
                })
            
            return {
                'statusCode': 200,
                'body': json.dumps({'processed': results})
            }
        
        # Handle API Gateway or direct invocation
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
        
        # Get session_id
        session_id = body.get('session_id')
        
        # Try path parameters
        if not session_id and 'pathParameters' in event:
            session_id = event['pathParameters'].get('session_id')
        
        if not session_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'session_id is required'
                })
            }
        
        logger.info(f"[Service12] Processing session: {session_id}")
        
        # Generate slides
        slides = generate_slides_from_session(session_id)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'session_id': session_id,
                'slides_count': len(slides),
                'slides': slides
            })
        }
        
    except ValueError as e:
        logger.error(f"[Service12] ❌ Validation error: {e}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
        
    except Exception as e:
        logger.error(f"[Service12] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
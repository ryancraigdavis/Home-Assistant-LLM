#!/usr/bin/env python3
"""
Discover Home Assistant entities and generate bridge configuration
"""
import os
import json
import requests
from typing import Dict, List

def discover_ha_entities():
    """Fetch all entities from Home Assistant API"""
    
    ha_host = os.getenv("HA_HOST")
    ha_token = os.getenv("HA_TOKEN")
    
    if not ha_host or not ha_token:
        print("Please set HA_HOST and HA_TOKEN environment variables")
        return None
    
    url = f"http://{ha_host}:8123/api/states"
    headers = {"Authorization": f"Bearer {ha_token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching entities: {e}")
        return None

def categorize_entities(entities):
    """Categorize entities by domain and controllability"""
    
    categories = {
        'lights': [],
        'switches': [], 
        'climate': [],
        'fans': [],
        'automations': [],
        'scripts': [],
        'media_players': [],
        'covers': [],
        'sensors': [],
        'other': []
    }
    
    for entity in entities:
        entity_id = entity['entity_id']
        domain = entity_id.split('.')[0]
        friendly_name = entity.get('attributes', {}).get('friendly_name', entity_id)
        
        entity_info = {
            'entity_id': entity_id,
            'friendly_name': friendly_name,
            'state': entity['state']
        }
        
        if domain == 'light':
            categories['lights'].append(entity_info)
        elif domain == 'switch':
            categories['switches'].append(entity_info)
        elif domain == 'climate':
            categories['climate'].append(entity_info)
        elif domain == 'fan':
            categories['fans'].append(entity_info)
        elif domain == 'automation':
            categories['automations'].append(entity_info)
        elif domain == 'script':
            categories['scripts'].append(entity_info)
        elif domain == 'media_player':
            categories['media_players'].append(entity_info)
        elif domain == 'cover':
            categories['covers'].append(entity_info)
        elif domain in ['sensor', 'binary_sensor']:
            categories['sensors'].append(entity_info)
        else:
            categories['other'].append(entity_info)
    
    return categories

def generate_system_prompt(categories):
    """Generate system prompt with discovered entities"""
    
    prompt_entities = []
    
    # Add controllable entities
    for light in categories['lights']:
        prompt_entities.append(f"- {light['entity_id']} ({light['friendly_name']})")
    
    for switch in categories['switches']:
        prompt_entities.append(f"- {switch['entity_id']} ({switch['friendly_name']})")
        
    for climate in categories['climate']:
        prompt_entities.append(f"- {climate['entity_id']} ({climate['friendly_name']})")
        
    for fan in categories['fans']:
        prompt_entities.append(f"- {fan['entity_id']} ({fan['friendly_name']})")
        
    for automation in categories['automations']:
        prompt_entities.append(f"- {automation['entity_id']} ({automation['friendly_name']})")
        
    for script in categories['scripts']:
        prompt_entities.append(f"- {script['entity_id']} ({script['friendly_name']})")
    
    return "\n".join(prompt_entities)

def main():
    print("Discovering Home Assistant entities...")
    
    entities = discover_ha_entities()
    if not entities:
        return
    
    categories = categorize_entities(entities)
    
    # Save discovery results
    with open('ha_entities.json', 'w') as f:
        json.dump(categories, f, indent=2)
    
    # Generate system prompt
    entity_list = generate_system_prompt(categories)
    
    print(f"\nFound {len(entities)} total entities:")
    print(f"- Lights: {len(categories['lights'])}")
    print(f"- Switches: {len(categories['switches'])}")
    print(f"- Climate: {len(categories['climate'])}")
    print(f"- Fans: {len(categories['fans'])}")
    print(f"- Automations: {len(categories['automations'])}")
    print(f"- Scripts: {len(categories['scripts'])}")
    print(f"- Media Players: {len(categories['media_players'])}")
    print(f"- Covers: {len(categories['covers'])}")
    print(f"- Sensors: {len(categories['sensors'])}")
    print(f"- Other: {len(categories['other'])}")
    
    print(f"\nEntity list saved to ha_entities.json")
    print(f"Generated system prompt saved to ha_entities.txt")
    
    # Save system prompt
    with open('ha_entities.txt', 'w') as f:
        f.write("Current available entities:\n")
        f.write(entity_list)

if __name__ == "__main__":
    main()
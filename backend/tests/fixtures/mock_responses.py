"""
Mock API responses for external services
"""

FIREFLIES_TRANSCRIPTS_LIST_RESPONSE = {
    "data": {
        "transcripts": [
            {
                "id": "trans_123",
                "title": "Sales Call with Client",
                "date": "2024-01-15T10:00:00Z",
                "duration": 1800,
                "participants": [
                    {"name": "John Doe", "email": "john@company.com"},
                    {"name": "Jane Smith", "email": "jane@client.com"}
                ]
            },
            {
                "id": "trans_124",
                "title": "Product Planning Meeting",
                "date": "2024-01-16T14:00:00Z",
                "duration": 3600,
                "participants": [
                    {"name": "Alice Johnson", "email": "alice@company.com"}
                ]
            }
        ]
    }
}

FIREFLIES_TRANSCRIPT_DETAIL_RESPONSE = {
    "data": {
        "transcript": {
            "id": "trans_123",
            "title": "Q4 Planning Meeting",
            "date": "2024-01-15T10:00:00Z",
            "duration": 3600,
            "transcript_text": "Welcome everyone to the Q4 planning meeting. We need to discuss our sales targets and strategies for the upcoming quarter.",
            "sentences": [
                {
                    "text": "Welcome everyone to the Q4 planning meeting",
                    "speaker_name": "John Smith",
                    "start_time": 0
                },
                {
                    "text": "We need to discuss our sales targets",
                    "speaker_name": "John Smith",
                    "start_time": 5
                },
                {
                    "text": "I agree, we should focus on enterprise clients",
                    "speaker_name": "Jane Doe",
                    "start_time": 10
                }
            ],
            "participants": [
                {"name": "John Smith", "email": "john@company.com"},
                {"name": "Jane Doe", "email": "jane@company.com"},
                {"name": "Bob Wilson", "email": "bob@company.com"}
            ],
            "summary": "Discussion about Q4 sales goals, target enterprise clients, and marketing strategies.",
            "action_items": [
                "Follow up with potential enterprise clients",
                "Prepare Q4 sales deck",
                "Schedule follow-up meeting"
            ],
            "keywords": ["sales", "targets", "enterprise", "Q4", "strategy"]
        }
    }
}

PIPEDRIVE_FIELDS_RESPONSE = {
    "success": True,
    "data": [
        {
            "id": 1,
            "key": "title",
            "name": "Deal Title",
            "field_type": "varchar",
            "is_required": True,
            "edit_flag": True
        },
        {
            "id": 2,
            "key": "value",
            "name": "Deal Value",
            "field_type": "monetary",
            "is_required": False,
            "edit_flag": True
        },
        {
            "id": 3,
            "key": "person_id",
            "name": "Person",
            "field_type": "person",
            "is_required": False,
            "edit_flag": True
        },
        {
            "id": 4,
            "key": "org_id",
            "name": "Organization",
            "field_type": "org",
            "is_required": False,
            "edit_flag": True
        },
        {
            "id": 5,
            "key": "stage_id",
            "name": "Stage",
            "field_type": "stage",
            "is_required": True,
            "edit_flag": True
        }
    ]
}

PIPEDRIVE_STAGES_RESPONSE = {
    "success": True,
    "data": [
        {
            "id": 1,
            "name": "Lead",
            "pipeline_id": 1,
            "pipeline_name": "Sales Pipeline",
            "order_nr": 1
        },
        {
            "id": 2,
            "name": "Qualified",
            "pipeline_id": 1,
            "pipeline_name": "Sales Pipeline",
            "order_nr": 2
        },
        {
            "id": 3,
            "name": "Proposal",
            "pipeline_id": 1,
            "pipeline_name": "Sales Pipeline",
            "order_nr": 3
        },
        {
            "id": 4,
            "name": "Won",
            "pipeline_id": 1,
            "pipeline_name": "Sales Pipeline",
            "order_nr": 4
        }
    ]
}

PIPEDRIVE_USERS_RESPONSE = {
    "success": True,
    "data": [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@company.com",
            "active_flag": True
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@company.com",
            "active_flag": True
        }
    ]
}

PIPEDRIVE_CURRENCIES_RESPONSE = {
    "success": True,
    "data": [
        {
            "code": "USD",
            "name": "US Dollar",
            "symbol": "$"
        },
        {
            "code": "EUR",
            "name": "Euro",
            "symbol": "€"
        },
        {
            "code": "GBP",
            "name": "British Pound",
            "symbol": "£"
        }
    ]
}

PIPEDRIVE_CREATE_DEAL_RESPONSE = {
    "success": True,
    "data": {
        "id": 123,
        "title": "Enterprise Deal - Acme Corp",
        "value": 50000,
        "currency": "USD",
        "status": "open",
        "stage_id": 1,
        "person_id": 456,
        "org_id": 789,
        "add_time": "2024-01-15 10:00:00",
        "update_time": "2024-01-15 10:00:00"
    }
}

OPENAI_COMPLETION_RESPONSE = {
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "gpt-4",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": '{"participant_names": ["John Smith", "Jane Doe"], "topics": ["Q4 planning", "sales targets"], "action_items": ["Follow up with clients", "Prepare sales deck"]}'
        },
        "finish_reason": "stop"
    }],
    "usage": {
        "prompt_tokens": 150,
        "completion_tokens": 80,
        "total_tokens": 230
    }
}

ANTHROPIC_COMPLETION_RESPONSE = {
    "id": "msg_123",
    "type": "message",
    "role": "assistant",
    "content": [{
        "type": "text",
        "text": '{"summary": "Meeting about Q4 sales strategy", "key_points": ["Enterprise focus", "Increase targets by 20%"]}'
    }],
    "model": "claude-3-sonnet-20240229",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 100,
        "output_tokens": 50
    }
}

GROQ_COMPLETION_RESPONSE = {
    "id": "chatcmpl-456",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "mixtral-8x7b-32768",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "This is a generated summary of the meeting transcript."
        },
        "finish_reason": "stop"
    }]
}

# ============================================================================
# AI SERVICE ADDITIONS FOR EMAIL SEQUENCES
# Add these functions to the END of your backend/ai_service.py file
# ============================================================================

async def generate_sequence_emails(
    transcript_summary: Dict[str, Any],
    num_emails: int = 3,
    custom_prompt: Optional[str] = None,
    tone: str = "professional",
    include_variables: List[str] = None,
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Generate email sequence content using AI based on transcript summary.
    
    Args:
        transcript_summary: Extracted information from the transcript
        num_emails: Number of emails to generate (default 3)
        custom_prompt: Custom instructions for generation
        tone: Email tone (professional, friendly, formal, casual)
        include_variables: List of variables to include in emails
        workflow_id: Workflow ID for universal rules
    
    Returns:
        Dict with emails and generation metadata
    """
    try:
        api_key = get_claude_client()
        
        # Get universal rules if workflow_id provided
        universal_rules = ""
        if workflow_id:
            try:
                from database import get_db
                import models
                db = next(get_db())
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if workflow and workflow.universal_rules:
                    universal_rules = workflow.universal_rules.strip()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")
        
        # Build the prompt
        summary_json = json.dumps(transcript_summary, indent=2)
        
        variables_section = ""
        if include_variables:
            variables_section = f"""
Use these extracted variables in the emails where appropriate:
{', '.join(include_variables)}

For each variable, use the format {{{{variable_name}}}} in the email content.
"""

        tone_guidance = {
            "professional": "Maintain a professional, business-appropriate tone. Be clear and concise.",
            "friendly": "Use a warm, approachable tone while remaining professional. Add personality.",
            "formal": "Use formal business language. Be respectful and traditional in style.",
            "casual": "Use a conversational, relaxed tone while still being professional."
        }
        
        system_prompt = f"""You are an expert sales copywriter who specializes in follow-up email sequences.
{universal_rules if universal_rules else ""}

TONE GUIDANCE: {tone_guidance.get(tone, tone_guidance['professional'])}
"""

        user_prompt = f"""Based on this meeting transcript summary, generate a {num_emails}-email follow-up sequence.

TRANSCRIPT SUMMARY:
{summary_json}

{variables_section}

{custom_prompt if custom_prompt else ""}

Generate {num_emails} emails with strategic timing recommendations. Each email should:
1. Build on the previous email
2. Reference specific points from the meeting
3. Provide value (not just "checking in")
4. Have a clear call-to-action

Return a JSON object with this exact structure:
{{
    "emails": [
        {{
            "order": 1,
            "name": "Initial Follow-up",
            "subject": "Subject line here",
            "body": "Email body with {{{{variable}}}} placeholders",
            "timing_recommendation": {{
                "delay_value": 1,
                "delay_unit": "days",
                "reasoning": "Why this timing"
            }},
            "purpose": "Brief description of this email's goal"
        }}
    ],
    "sequence_strategy": "Brief explanation of the overall sequence strategy"
}}

Return ONLY the JSON object, no additional text."""

        logger.info(f"Generating {num_emails} sequence emails with AI")
        
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ]
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            ai_response = result["content"][0]["text"].strip()
            
            # Clean up response
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()
            
            try:
                generated_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}. Response: {cleaned_response[:500]}")
                raise Exception("Failed to parse AI response")
            
            logger.info(f"Successfully generated {len(generated_data.get('emails', []))} emails")
            
            return {
                "emails": generated_data.get("emails", []),
                "generation_metadata": {
                    "sequence_strategy": generated_data.get("sequence_strategy", ""),
                    "tone": tone,
                    "num_emails_requested": num_emails,
                    "num_emails_generated": len(generated_data.get("emails", []))
                }
            }
            
    except Exception as e:
        raise handle_anthropic_error(e, "email sequence generation")


async def optimize_email_timing(
    transcript_summary: Dict[str, Any],
    emails: List[Dict[str, Any]],
    custom_prompt: Optional[str] = None,
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Use AI to optimize the timing of emails in a sequence based on transcript context.
    
    Args:
        transcript_summary: Extracted information from the transcript
        emails: List of emails with current timing
        custom_prompt: Custom instructions for timing optimization
        workflow_id: Workflow ID for universal rules
    
    Returns:
        Dict with optimized timing recommendations and reasoning
    """
    try:
        api_key = get_claude_client()
        
        # Get universal rules if workflow_id provided
        universal_rules = ""
        if workflow_id:
            try:
                from database import get_db
                import models
                db = next(get_db())
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if workflow and workflow.universal_rules:
                    universal_rules = workflow.universal_rules.strip()
            except Exception as e:
                logger.warning(f"Could not fetch universal rules: {str(e)}")
        
        summary_json = json.dumps(transcript_summary, indent=2)
        emails_json = json.dumps(emails, indent=2)
        
        system_prompt = f"""You are an expert in sales psychology and email timing optimization.
Your goal is to recommend optimal timing for follow-up emails based on the context of sales conversations.
{universal_rules if universal_rules else ""}

Consider factors like:
- Urgency signals from the conversation
- Decision timeline mentioned
- Day of week effectiveness (Tue-Thu typically best)
- Time between touches (not too aggressive, not too sparse)
- Buyer engagement level
"""

        user_prompt = f"""Analyze this transcript summary and current email sequence timing.
Recommend optimal timing adjustments.

TRANSCRIPT SUMMARY:
{summary_json}

CURRENT EMAIL SEQUENCE:
{emails_json}

{custom_prompt if custom_prompt else ""}

Return a JSON object with this structure:
{{
    "optimized_timing": [
        {{
            "email_order": 1,
            "original_delay": "1 days",
            "recommended_delay_value": 1,
            "recommended_delay_unit": "days",
            "recommended_day": null,
            "recommended_time": "10:00",
            "confidence": "high",
            "reasoning": "Why this timing is optimal"
        }}
    ],
    "reasoning": "Overall strategy explanation",
    "urgency_detected": "high/medium/low",
    "decision_timeline": "immediate/short-term/long-term/unknown"
}}

Return ONLY the JSON object."""

        logger.info("Optimizing email timing with AI")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 2048,
                    "system": system_prompt,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ]
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            ai_response = result["content"][0]["text"].strip()
            
            # Clean up response
            cleaned_response = ai_response
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.replace("```", "").strip()
            
            try:
                timing_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}. Response: {cleaned_response[:500]}")
                raise Exception("Failed to parse AI timing response")
            
            logger.info(f"Successfully optimized timing for {len(timing_data.get('optimized_timing', []))} emails")
            
            return {
                "optimized_timing": timing_data.get("optimized_timing", []),
                "reasoning": timing_data.get("reasoning", ""),
                "metadata": {
                    "urgency_detected": timing_data.get("urgency_detected", "unknown"),
                    "decision_timeline": timing_data.get("decision_timeline", "unknown")
                }
            }
            
    except Exception as e:
        raise handle_anthropic_error(e, "email timing optimization")


async def check_sequence_skip_conditions(
    skip_conditions: List[Dict[str, Any]],
    context_data: Dict[str, Any],
    workflow_id: int = None
) -> Dict[str, Any]:
    """
    Check if a sequence should be skipped based on conditions and context.
    
    Args:
        skip_conditions: List of skip condition rules
        context_data: Context including CRM data, transcript data, etc.
        workflow_id: Workflow ID for logging
    
    Returns:
        Dict with should_skip boolean and reason
    """
    try:
        for condition in skip_conditions:
            condition_type = condition.get("type")
            operator = condition.get("operator")
            value = condition.get("value")
            field = condition.get("field")
            
            # Get the actual value from context
            if condition_type == "deal_stage":
                actual_value = context_data.get("deal", {}).get("stage_id") or context_data.get("deal", {}).get("stage")
            elif condition_type == "deal_status":
                actual_value = context_data.get("deal", {}).get("status")
            elif condition_type == "contact_field":
                actual_value = context_data.get("contact", {}).get(field)
            elif condition_type == "reply_received":
                actual_value = context_data.get("reply_received", False)
            elif condition_type == "days_since_last_email":
                actual_value = context_data.get("days_since_last_email", 0)
            else:
                logger.warning(f"Unknown skip condition type: {condition_type}")
                continue
            
            # Evaluate condition
            skip = False
            if operator == "equals":
                skip = str(actual_value).lower() == str(value).lower()
            elif operator == "not_equals":
                skip = str(actual_value).lower() != str(value).lower()
            elif operator == "contains":
                skip = str(value).lower() in str(actual_value).lower()
            elif operator == "greater_than":
                skip = float(actual_value or 0) > float(value)
            elif operator == "less_than":
                skip = float(actual_value or 0) < float(value)
            elif operator == "is_true":
                skip = bool(actual_value) == True
            elif operator == "is_false":
                skip = bool(actual_value) == False
            
            if skip:
                reason = f"Skip condition met: {condition_type} {operator} {value}"
                logger.info(f"Sequence skip triggered for workflow {workflow_id}: {reason}")
                return {
                    "should_skip": True,
                    "reason": reason,
                    "condition": condition
                }
        
        return {
            "should_skip": False,
            "reason": None,
            "condition": None
        }
        
    except Exception as e:
        logger.error(f"Error checking skip conditions: {str(e)}")
        # Don't skip on error - let the sequence proceed
        return {
            "should_skip": False,
            "reason": f"Error checking conditions: {str(e)}",
            "condition": None
        }

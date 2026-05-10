from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import re

from database import get_db
from auth import get_current_active_user
import models

router = APIRouter()

class ExtractedVariable(BaseModel):
    id: int
    variable_name: str
    variable_key: str
    variable_value: Any
    data_type: str
    execution_id: int
    created_at: str

    class Config:
        from_attributes = True

class VariableSubstitution(BaseModel):
    text: str

class VariableSubstitutionResponse(BaseModel):
    processed_text: str
    substitutions_made: int
    variables_used: List[str]

def verify_workflow_ownership(workflow_id: int, current_user: models.User, db: Session):
    """Role-aware workflow access check. Delegates to auth.verify_workflow_access."""
    from auth import verify_workflow_access
    return verify_workflow_access(workflow_id, current_user, db)

async def substitute_variables_in_text(text: str, workflow_id: int) -> str:
    """Helper function to substitute variables in text for component execution"""
    from database import SessionLocal
    
    if not workflow_id or not text:
        return text
    
    db = SessionLocal()
    try:
        # Get all available variables for this workflow
        variables = db.query(models.ExtractedVariable).filter(
            models.ExtractedVariable.workflow_id == workflow_id
        ).order_by(
            models.ExtractedVariable.variable_name,
            models.ExtractedVariable.created_at.desc()
        ).all()
        
        # Create a mapping of latest variables
        latest_variables = {}
        for var in variables:
            if var.variable_name not in latest_variables:
                latest_variables[var.variable_name] = var
        
        # Find all {{VariableName}} patterns
        pattern = r'\{\{([^}]+)\}\}'

        def replace_variable(match):
            var_name = match.group(1).strip()

            # Find matching variable (case insensitive, flexible with spaces and underscores)
            for stored_var_name, var_obj in latest_variables.items():
                if stored_var_name.lower().replace(" ", "_") == var_name.lower().replace(" ", "_"):
                    # Format the value based on data type
                    value = var_obj.variable_value
                    if var_obj.data_type == "array" and isinstance(value, list):
                        return ", ".join(str(item) for item in value)
                    elif var_obj.data_type == "boolean":
                        return "Yes" if value else "No"
                    elif value is None:
                        return "[Not Available]"
                    else:
                        return str(value)

            # If no variable found, leave the placeholder as-is
            return match.group(0)
        
        return re.sub(pattern, replace_variable, text)
        
    finally:
        db.close()

@router.get("/workflows/{workflow_id}/variables", response_model=List[ExtractedVariable])
async def get_workflow_variables(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all available extracted variables for a workflow"""
    verify_workflow_ownership(workflow_id, current_user, db)
    
    # Get latest variables for each variable name (most recent execution)
    variables = db.query(models.ExtractedVariable).filter(
        models.ExtractedVariable.workflow_id == workflow_id
    ).order_by(
        models.ExtractedVariable.variable_name,
        models.ExtractedVariable.created_at.desc()
    ).all()
    
    # Keep only the most recent variable for each name
    unique_variables = {}
    for var in variables:
        if var.variable_name not in unique_variables:
            unique_variables[var.variable_name] = var
    
    return list(unique_variables.values())

@router.post("/workflows/{workflow_id}/variables/substitute", response_model=VariableSubstitutionResponse)
async def substitute_variables(
    workflow_id: int,
    substitution_request: VariableSubstitution,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Replace variable placeholders in text with actual extracted values"""
    verify_workflow_ownership(workflow_id, current_user, db)
    
    text = substitution_request.text
    substitutions_made = 0
    variables_used = []
    
    # Get all available variables for this workflow
    variables = db.query(models.ExtractedVariable).filter(
        models.ExtractedVariable.workflow_id == workflow_id
    ).order_by(
        models.ExtractedVariable.variable_name,
        models.ExtractedVariable.created_at.desc()
    ).all()
    
    # Create a mapping of latest variables
    latest_variables = {}
    for var in variables:
        if var.variable_name not in latest_variables:
            latest_variables[var.variable_name] = var
    
    # Replace variables in text
    import re

    # Find all {{VariableName}} patterns
    pattern = r'\{\{([^}]+)\}\}'

    def replace_variable(match):
        nonlocal substitutions_made, variables_used

        var_name = match.group(1).strip()

        # Find matching variable (case insensitive, flexible with spaces and underscores)
        for stored_var_name, var_obj in latest_variables.items():
            if stored_var_name.lower().replace(" ", "_") == var_name.lower().replace(" ", "_"):
                substitutions_made += 1
                variables_used.append(stored_var_name)

                # Format the value based on data type
                value = var_obj.variable_value
                if var_obj.data_type == "array" and isinstance(value, list):
                    return ", ".join(str(item) for item in value)
                elif var_obj.data_type == "boolean":
                    return "Yes" if value else "No"
                elif value is None:
                    return "[Not Available]"
                else:
                    return str(value)

        # If no variable found, leave the placeholder as-is
        return match.group(0)
    
    processed_text = re.sub(pattern, replace_variable, text)
    
    return VariableSubstitutionResponse(
        processed_text=processed_text,
        substitutions_made=substitutions_made,
        variables_used=list(set(variables_used))  # Remove duplicates
    )
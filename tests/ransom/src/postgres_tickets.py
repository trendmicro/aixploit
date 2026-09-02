#!/usr/bin/env python3
"""
Python function to insert tickets into PostgreSQL database
"""
import os
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, Dict, Any

from lib.logger import get_logger

logger = get_logger()

def get_db_connection(database_url: str):
  """
  Get database connection using DATABASE_URL environment variable or default.
  """
  return psycopg2.connect(database_url)


def save_customer_table(database_url: str, filepath: str) -> bool:
  """Save customer table to a file in the run directory."""
  
  try:
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Query all customers
    cursor.execute("SELECT * FROM customers ORDER BY customer_id")
    customers = cursor.fetchall()
    
    # Convert to list of dicts
    customers_data = [dict(row) for row in customers]
    
    # Save as JSON
    with open(filepath, 'w', encoding='utf-8') as f:
      json.dump(customers_data, f, indent=2, default=str)
    
    cursor.close()
    conn.close()
    
    logger.info(f"Saved customer table to {filepath}")
    return True
    
  except psycopg2.Error as e:
    logger.error(f"Error saving customer table: {e}")
    return False
  except Exception as e:
    logger.error(f"Unexpected error saving customer table: {e}")
    return False



def generate_ticket_number(cursor) -> str:
  """
  Generate a unique ticket number in format T-XXXXXX.
  Similar to the Node.js implementation.
  """
  # Try to find the next available ticket number
  for attempt in range(100):
    cursor.execute(
      "SELECT MAX(CAST(SUBSTRING(ticket_number FROM 3) AS INTEGER)) AS max_num "
      "FROM tickets WHERE ticket_number LIKE 'T-%'"
    )
    result = cursor.fetchone()
    max_num = result.get('max_num', 0)
    next_num = int(max_num) + 1
    ticket_number = f"T-{str(next_num).zfill(6)}"
    
    # Check if this number already exists
    cursor.execute(
      "SELECT COUNT(*) AS count FROM tickets WHERE ticket_number = %s",
      (ticket_number,)
    )
    count = cursor.fetchone()['count']
    if count == 0:
      return ticket_number
  
  # Fallback to UUID-based if we can't find a sequential number
  return f"T-{uuid.uuid4().hex[:8].upper()}"


def insert_ticket(
  database_url: str,
  subject: str,
  description: str,
  priority: str = 'medium',
  status: str = 'open',
  category: Optional[str] = None,
  email: Optional[str] = None
) -> Dict[str, Any]:
  """
  Insert a ticket into the PostgreSQL database.

  Args:
    subject: Ticket subject (required)
    description: Ticket description (required)
    priority: Ticket priority - 'low', 'medium', or 'high' (default: 'medium')
    status: Ticket status - 'open', 'pending', or 'closed' (default: 'open')
    category: Ticket category (optional)
    email: Customer email address (optional)

  Returns:
    Dictionary containing the inserted ticket information and 'status' key with 'success' or error message
  """
  # Validate required fields
  if not subject or not subject.strip():
    return {'status': 'subject is required'}
  if not description or not description.strip():
    return {'status': 'description is required'}

  # Validate priority
  priority_lower = priority.lower() if priority else 'medium'
  if priority_lower not in ['low', 'medium', 'high']:
    return {'status': "priority must be 'low', 'medium', or 'high'"}

  # Validate status
  status_lower = status.lower() if status else 'open'
  if status_lower not in ['open', 'pending', 'closed']:
    return {'status': "status must be 'open', 'pending', or 'closed'"}

  conn = None
  cursor = None

  try:
    conn = get_db_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Retry logic to handle potential race conditions
    for attempt in range(5):
      try:
        # Generate ticket number
        ticket_number = generate_ticket_number(cursor)

        # Set current timestamp
        now = datetime.now()
        customer_name = 'John Doe'  # Default username (matching Node.js implementation)

        # Insert ticket
        cursor.execute(
          """
          INSERT INTO tickets (
            ticket_number, customer_id, customer_name, customer_email, subject, description,
            priority, status, category, assigned_to, created_at, updated_at
          ) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
          RETURNING id
          """,
          (
            ticket_number,
            customer_name,
            email or '',
            subject.strip(),
            description.strip(),
            priority_lower,
            status_lower,
            category or '',
            '',  # assigned_to
            now,
            now
          )
        )

        ticket_id = cursor.fetchone()['id']
        conn.commit()

        # Fetch the complete ticket record
        cursor.execute(
          """
          SELECT id, ticket_number, customer_name, customer_email, subject, priority, status,
                 category, assigned_to, created_at, updated_at
          FROM tickets WHERE id = %s
          """,
          (ticket_id,)
        )

        ticket = cursor.fetchone()
        result = dict(ticket)
        result['status'] = 'success'
        logger.info(f"Ticket inserted: {ticket_number}")
  
        return result

      except psycopg2.IntegrityError as e:
        # Check if it's a unique constraint violation on ticket_number
        if e.pgcode == '23505' and 'tickets_ticket_number_key' in str(e):
          conn.rollback()
          if attempt < 4:
            continue  # Retry with a new ticket number
          else:
            return {'status': 'Failed to create ticket after multiple attempts'}
        else:
          return {'status': f'Database integrity error: {str(e)}'}

  except psycopg2.Error as e:
    if conn:
      conn.rollback()
    return {'status': f'Database error: {str(e)}'}

  finally:
    if cursor:
      cursor.close()
    if conn:
      conn.close()

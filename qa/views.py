from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from documents.models import Document
from .services import QAService
from .models import QAHistory
import json


@login_required
def ask_question(request):
    """Handle Q&A requests"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=405)

    question = request.POST.get('question', '').strip()
    document_ids = request.POST.getlist('document_ids[]')

    if not question:
        return JsonResponse({'error': 'Question is required'}, status=400)

    # Convert document_ids to integers if provided
    if document_ids:
        try:
            document_ids = [int(doc_id) for doc_id in document_ids if doc_id]
        except ValueError:
            return JsonResponse({'error': 'Invalid document IDs'}, status=400)

    # Verify user owns the documents
    if document_ids:
        user_docs = set(
            Document.objects.filter(
                id__in=document_ids,
                user=request.user
            ).values_list('id', flat=True)
        )
        if set(document_ids) != user_docs:
            return JsonResponse({'error': 'Access denied to one or more documents'}, status=403)

    # Get answer
    qa_service = QAService()
    result = qa_service.answer_question(request.user, question, document_ids)

    return JsonResponse(result)


@login_required
def qa_history(request):
    """Get user's Q&A history"""
    limit = int(request.GET.get('limit', 20))
    offset = int(request.GET.get('offset', 0))

    history = QAHistory.objects.filter(
        user=request.user
    ).order_by('-created_at')[offset:offset + limit]

    results = []
    for item in history:
        citations = []
        try:
            citations_data = json.loads(item.citations) if item.citations else []
            for citation in citations_data:
                citations.append({
                    'document_id': citation.get('document_id'),
                    'chunk_id': citation.get('chunk_id'),
                    'start_offset': citation.get('start_offset'),
                    'end_offset': citation.get('end_offset')
                })
        except json.JSONDecodeError:
            pass

        results.append({
            'id': item.id,
            'question': item.question,
            'answer': item.answer,
            'citations': citations,
            'document_ids': item.document_ids,
            'chunk_ids': item.chunk_ids,
            'created_at': item.created_at.isoformat()
        })

    # Get total count
    total = QAHistory.objects.filter(user=request.user).count()

    return JsonResponse({
        'history': results,
        'total': total,
        'offset': offset,
        'limit': limit
    })


@login_required
def delete_qa_history(request, history_id):
    """Delete a Q&A history item"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE request required'}, status=405)

    try:
        item = QAHistory.objects.get(id=history_id, user=request.user)
        item.delete()
        return JsonResponse({'success': True})
    except QAHistory.DoesNotExist:
        return JsonResponse({'error': 'History item not found'}, status=404)

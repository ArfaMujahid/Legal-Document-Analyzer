from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from documents.models import Document, TextChunk
from search.models import SearchHistory
from processing.vector_service import VectorService
import json


@login_required
def search_view(request):
    """Display search page"""
    return render(request, 'search/search.html')


@require_POST
@login_required
def keyword_search(request):
    """Perform keyword search on document text"""
    query = request.POST.get('query', '').strip()
    document_id = request.POST.get('document_id')
    filters = json.loads(request.POST.get('filters', '{}'))

    if not query:
        return JsonResponse({'error': 'Query is required'}, status=400)

    # Build base query
    chunks_query = Q(document__user=request.user)

    # Filter by document if specified
    if document_id:
        chunks_query &= Q(document_id=document_id)

    # Filter by document type
    if filters.get('file_type'):
        chunks_query &= Q(document__file_type__iexact=filters['file_type'])

    # Perform keyword search
    chunks = TextChunk.objects.filter(chunks_query).filter(
        Q(text__icontains=query)
    ).select_related('document').order_by('document__upload_time', 'chunk_index')

    # Format results
    results = []
    for chunk in chunks:
        # Get snippet around query
        text = chunk.text
        query_lower = query.lower()
        query_pos = text.lower().find(query_lower)

        snippet = text
        if query_pos > 0:
            start = max(0, query_pos - 100)
            end = min(len(text), query_pos + len(query) + 100)
            snippet = text[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."

        results.append({
            'chunk_id': chunk.id,
            'document_id': chunk.document.id,
            'document_title': chunk.document.title or chunk.document.file_name,
            'document_type': chunk.document.file_type,
            'snippet': snippet,
            'start_offset': chunk.start_offset,
            'end_offset': chunk.end_offset,
            'chunk_index': chunk.chunk_index
        })

    # Log search
    SearchHistory.objects.create(
        user=request.user,
        search_type='keyword',
        query=query,
        filters=filters,
        results_count=len(results)
    )

    return JsonResponse({
        'results': results,
        'total': len(results),
        'search_type': 'keyword'
    })


@require_POST
@login_required
def semantic_search(request):
    """Perform semantic search using vector embeddings"""
    query = request.POST.get('query', '').strip()
    document_id = request.POST.get('document_id')
    filters = json.loads(request.POST.get('filters', '{}'))

    if not query:
        return JsonResponse({'error': 'Query is required'}, status=400)

    try:
        vector_service = VectorService()
        vector_service.ensure_collection_exists()

        # Perform semantic search
        results = vector_service.search_similar_chunks(
            query_text=query,
            user_id=request.user.id,
            document_id=document_id if document_id else None,
            limit=20
        )

        # Format results with document info
        formatted_results = []
        chunk_ids = [r['chunk_id'] for r in results]

        # Get chunk details from database
        chunks = TextChunk.objects.filter(
            id__in=chunk_ids,
            document__user=request.user
        ).select_related('document')

        # Create mapping
        chunk_map = {chunk.id: chunk for chunk in chunks}

        for result in results:
            chunk = chunk_map.get(result['chunk_id'])
            if chunk:
                # Apply additional filters
                if filters.get('file_type') and chunk.document.file_type != filters['file_type']:
                    continue

                formatted_results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document.id,
                    'document_title': chunk.document.title or chunk.document.file_name,
                    'document_type': chunk.document.file_type,
                    'snippet': chunk.text,
                    'start_offset': chunk.start_offset,
                    'end_offset': chunk.end_offset,
                    'chunk_index': chunk.chunk_index,
                    'score': round(result['score'], 3)
                })

        # Log search
        SearchHistory.objects.create(
            user=request.user,
            search_type='semantic',
            query=query,
            filters=filters,
            results_count=len(formatted_results)
        )

        return JsonResponse({
            'results': formatted_results,
            'total': len(formatted_results),
            'search_type': 'semantic'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def search_history(request):
    """Get user's search history"""
    history = SearchHistory.objects.filter(user=request.user).order_by('-created_at')[:20]

    results = []
    for item in history:
        results.append({
            'id': item.id,
            'search_type': item.search_type,
            'query': item.query,
            'results_count': item.results_count,
            'created_at': item.created_at.isoformat()
        })

    return JsonResponse({'history': results})

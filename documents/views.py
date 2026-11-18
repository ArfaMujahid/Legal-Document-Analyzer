from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q
from .models import Document, DocumentFile, TextChunk
from .forms import DocumentUploadForm
from processing.tasks import DocumentProcessor
from processing.vector_service import VectorService
from processing.answer_service import AnswerService
from search.models import SearchHistory
import os
import mimetypes
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def dashboard_view(request):
    """Display user's document library"""
    documents = Document.objects.filter(user=request.user).order_by('-upload_time')

    # Apply filters
    file_type = request.GET.get('type')
    if file_type:
        documents = documents.filter(file_type__iexact=file_type)

    date_range = request.GET.get('date_range')
    if date_range:
        try:
            start_date, end_date = date_range.split(' to ')
            from datetime import datetime
            if start_date:
                documents = documents.filter(upload_time__gte=datetime.strptime(start_date, '%Y-%m-%d'))
            if end_date:
                documents = documents.filter(upload_time__lte=datetime.strptime(end_date, '%Y-%m-%d'))
        except ValueError:
            pass  # Invalid date format, ignore filter

    return render(request, 'documents/dashboard.html', {'documents': documents})


@login_required
def upload_view(request):
    """Handle document upload"""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.user = request.user
            document.file_name = form.cleaned_data['file'].name
            document.file_type = form.cleaned_data['file'].name.split('.')[-1].lower()
            document.file_size = form.cleaned_data['file'].size
            document.delete_at = timezone.now() + timezone.timedelta(days=60)
            document.save()

            # Create DocumentFile record
            DocumentFile.objects.create(
                document=document,
                storage_path=document.file.path,
            )

            # Start processing pipeline
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Starting processing for document: {document.file_name}")

            processor = DocumentProcessor(document)
            processing_success = processor.process()

            if processing_success and document.status == 'complete':
                messages.success(request, f'Document and processed successfully!')
            else:
                messages.error(request, f'Document "{document.file_name}" upload failed during processing. Please try again.')

            return redirect('documents:dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = DocumentUploadForm()
    return render(request, 'documents/upload.html', {'form': form})


@login_required
def document_view(request, document_id):
    """Display document details and extracted text"""
    document = get_object_or_404(Document, id=document_id, user=request.user)
    return render(request, 'documents/view.html', {'document': document})


@login_required
def sections_view(request, document_id):
    """Display document sections explorer"""
    document = get_object_or_404(Document, id=document_id, user=request.user)
    sections = document.section_set.all().order_by('start_offset')
    return render(request, 'documents/sections.html', {'document': document, 'sections': sections})


@login_required
def download_view(request, document_id):
    """Handle document download"""
    document = get_object_or_404(Document, id=document_id, user=request.user)
    document_file = get_object_or_404(DocumentFile, document=document)

    file_path = document_file.storage_path
    if not os.path.exists(file_path):
        raise Http404("File not found")

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=mimetypes.guess_type(file_path)[0])
        response['Content-Disposition'] = f'attachment; filename="{document.file_name}"'
        return response


@require_POST
@login_required
def delete_view(request, document_id):
    """Handle document deletion"""
    document = get_object_or_404(Document, id=document_id, user=request.user)
    document_file = DocumentFile.objects.filter(document=document).first()

    # Delete file from storage
    if document_file and os.path.exists(document_file.storage_path):
        os.remove(document_file.storage_path)

    # Delete vectors from Qdrant
    try:
        from processing.vector_service import VectorService
        vector_service = VectorService()
        vector_service.delete_document_vectors(document.id)
    except:
        pass  # Continue even if vector deletion fails

    document.delete()
    messages.success(request, 'Document deleted successfully!')
    return redirect('documents:dashboard')


@require_POST
@login_required
def keyword_search(request, document_id):
    """Perform keyword search within a specific document"""
    document = get_object_or_404(Document, id=document_id, user=request.user)

    if document.status != 'complete':
        return JsonResponse({'error': 'Document is not processed yet'}, status=400)

    query = request.POST.get('query', '').strip()
    if not query:
        return JsonResponse({'error': 'Query is required'}, status=400)

    # Perform keyword search within this document only
    chunks = TextChunk.objects.filter(
        document=document,
        text__icontains=query
    ).order_by('chunk_index')

    # Format results - remove overlapping chunks
    results = []
    prev_end = -1
    for chunk in chunks:
        # Skip if this chunk overlaps with the previous one
        if chunk.start_offset < prev_end:
            continue

        # For keyword search, show the full chunk text
        snippet = chunk.text

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

        prev_end = chunk.end_offset

    # Log search
    SearchHistory.objects.create(
        user=request.user,
        search_type='keyword',
        query=query,
        filters={'document_id': document_id},
        results_count=len(results)
    )

    return JsonResponse({
        'results': results,
        'total': len(results),
        'search_type': 'keyword',
        'document_title': document.title or document.file_name
    })


@require_POST
@login_required
def semantic_search(request, document_id):
    """Perform semantic search within a specific document"""
    document = get_object_or_404(Document, id=document_id, user=request.user)

    if document.status != 'complete':
        return JsonResponse({'error': 'Document is not processed yet'}, status=400)

    query = request.POST.get('query', '').strip()
    if not query:
        return JsonResponse({'error': 'Query is required'}, status=400)

    try:
        vector_service = VectorService()
        vector_service.ensure_collection_exists()

        # Perform semantic search within this document only
        results = vector_service.search_similar_chunks(
            query_text=query,
            user_id=request.user.id,
            document_id=document_id,  # Restrict to this document
            limit=20
        )

        # Format results
        formatted_results = []
        chunk_ids = [r['chunk_id'] for r in results]

        # Get chunk details from database
        chunks = TextChunk.objects.filter(
            id__in=chunk_ids,
            document=document
        )

        # Create mapping
        chunk_map = {chunk.id: chunk for chunk in chunks}

        for result in results:
            chunk = chunk_map.get(result['chunk_id'])
            if chunk:
                formatted_results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document.id,
                    'document_title': chunk.document.title or chunk.document.file_name,
                    'document_type': chunk.document.file_type,
                    'snippet': chunk.text,  # Pass complete chunk text to LLM
                    'start_offset': chunk.start_offset,
                    'end_offset': chunk.end_offset,
                    'chunk_index': chunk.chunk_index,
                    'score': round(result['score'], 3)
                })

        # Generate LLM answer if we have results and an LLM is configured
        answer = None
        if formatted_results and settings.OPENROUTER_API_KEY:
            try:
                answer_service = AnswerService()
                answer = answer_service.generate_answer(
                    query=query,
                    context_chunks=formatted_results,
                    document_title=document.title or document.file_name
                )
                logger.info(f"Generated LLM answer: {answer[:100]}...")  # Log first 100 chars
            except Exception as e:
                logger.error(f"Error generating LLM answer: {e}")

        # Log search
        SearchHistory.objects.create(
            user=request.user,
            search_type='semantic',
            query=query,
            filters={'document_id': document_id},
            results_count=len(formatted_results)
        )

        response_data = {
            'results': formatted_results,
            'total': len(formatted_results),
            'search_type': 'semantic',
            'document_title': document.title or document.file_name
        }

        if answer:
            response_data['answer'] = answer

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

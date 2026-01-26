from django import forms
from .models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'file']

    file = forms.FileField(
        label='Select Document',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx,.txt'
        })
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (25MB limit)
            if file.size > 25 * 1024 * 1024:
                raise forms.ValidationError("File size cannot exceed 25MB.")

            # Check file type
            file_extension = file.name.split('.')[-1].lower()
            allowed_extensions = ['pdf', 'docx', 'txt']
            if file_extension not in allowed_extensions:
                raise forms.ValidationError(
                    f"File type not allowed. Please upload a {', '.join(allowed_extensions)} file."
                )
        return file
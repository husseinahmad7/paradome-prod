from django.shortcuts import render
from django.template.loader import render_to_string
from django.core.mail import BadHeaderError, send_mail
from django.http import HttpResponse
from .forms import ContactMe

def home(request):
    return render(request, 'HusseinAh/myPortfolio.html')

def mailme(request):
    if request.method == 'POST':
        form = ContactMe(request.POST)
        if form.is_valid():
            subject = request.POST.get('subject', '')
            message = request.POST.get('content', '')
            from_email = request.POST.get('email', '')
            if subject and message and from_email:
                html = render_to_string('HusseinAh/mail.html',{'email':from_email,'message':message})
                try:
                    send_mail(subject, message, from_email, ['h7osanna.xyc@gmail.com'],html_message=html)
                except BadHeaderError:
                    return HttpResponse('<main><div class="notification is-success" role="alert">Invalid.. try again.</div></main>')
                return HttpResponse('<main><div class="notification is-success" role="alert">Thanks for your feedback</div></main>')
        
    else:
        form = ContactMe()
    context = {}
    
    context['form'] = form
    return render(request, 'HusseinAh/feedback.html', context)
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect, request
from django.urls import reverse
from django.contrib.auth import authenticate, login ,logout
# from . import forms
from django.contrib import messages
from .forms import UserRegisterForm, LoginForm, ProfileUpdateForm, UserUpdateForm
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.models import User


def index(request):
    
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse('users:login'))
    return render(request,'users/user.html',{'title':request.user.username})

# message = {}
def register_view(request):

    if request.method == 'POST':
        regForm = UserRegisterForm(request.POST)
        if regForm.is_valid():
            regForm.save()
            username= regForm.cleaned_data.get('username')
            messages.success(request,f'{username} Account created for you')
            # messages.error(request,'please try again')
            return redirect(reverse('users:register'))
    else:       
        regForm = UserRegisterForm()
    return render(request,'users/register.html',{'form':regForm})

# def login_page(request):
#     form = LoginForm()
#     # next = request.GET.get('next',reverse('users:index'))
#     if request.method == "POST":
#         username = request.POST['username']
#         password = request.POST['password']
#         user = authenticate(request, username=username, password=password)
#         if user is not None:
#             login(request, user)
#             # return redirect(next)
#             return redirect(reverse('users:index'))
#         else:
#             return render(request, 'users/login.html', {'next': next,'message': "invalid username or password",'title':'Login','form':form})
    
#     return render(request,'users/login.html',{'form':form})

def logout_view(request):
    logout(request)
    return render(request, 'users/login.html', {"message":"logged out",'form':LoginForm(),'title':'Login'})

@login_required
def profile_view(request):
    if request.method == 'POST':
            user_form =UserUpdateForm(request.POST, instance=request.user)
            profile_form =ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request,'your Account has been updated successfully.')
                return redirect(reverse('users:profile'))
    else:
        user_form =UserUpdateForm(instance=request.user)
        profile_form =ProfileUpdateForm(instance=request.user.profile)
    context = {'u_form':user_form,'p_form':profile_form}
    return render(request, 'users/profile.html', context)

def UserSearch(request):
    query = request.GET.get('q')
    context = {}
    if query:
        users = User.objects.filter(Q(username__icontains=query))
        paginator = Paginator(users,10)
        page_number = request.GET.get('page')
        users_pag = paginator.get_page(page_number)
        context = {'users': users_pag}
        
    return render(request, 'messages/search_user.html', context)
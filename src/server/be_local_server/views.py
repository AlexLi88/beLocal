import simplejson as sjson
from rest_framework import generics, status, viewsets, mixins, parsers, renderers, status, generics
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from rest_framework.authentication import get_authorization_header
from rest_framework.response import Response
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, HttpResponseServerError, Http404, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt
from django.db.models.base import ModelBase
from django.forms.models import model_to_dict
from social.apps.django_app.utils import psa
from secretballot import views
from secretballot.models import Vote
from be_local_server import serializers
from be_local_server.models import *
from haystack.query import SearchQuerySet
import datetime, json
from geopy.distance import vincenty
from operator import itemgetter, attrgetter, methodcaller
from taggit.models import Tag
from django.contrib.auth import authenticate
from django.core.files import File 
from PIL import Image
import urllib
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.views import password_reset, password_reset_confirm

class PasswordReset(GenericAPIView):
    permission_classes = (AllowAny,)

    """
    Calls Django Auth PasswordResetForm save method.

    Accepts the following POST parameters: email
    Returns the success/fail message.
    """

    serializer_class = serializers.PasswordResetSerializer

    def post(self, request):
        # Create a serializer with request.DATA
        serializer = self.serializer_class(data=request.DATA)

        try:
            user = User.objects.get(email=request.DATA['email']);
        except ObjectDoesNotExist:
            header = {"Access-Control-Expose-Headers": "Error-Message, Error-Type"}
            header["Error-Type"] = "email"
            header["Error-Message"] = "No user with this email exists in the system."
            return Response(headers=header, status=status.HTTP_400_BAD_REQUEST)

        if serializer.is_valid():
            # Create PasswordResetForm with the serializer
            reset_form = PasswordResetForm(data=serializer.data)

            if reset_form.is_valid():
                # Sett some values to trigger the send_email method.
                opts = {
                    'use_https': request.is_secure(),
                    'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL'),
                    'request': request,
                }

                reset_form.save(**opts)

                # Return the success message with OK HTTP status
                return Response(
                    {"success": "Password reset e-mail has been sent."},
                    status=status.HTTP_200_OK)

            else:
                    return Response(reset_form._errors,
                                    status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)

def reset_confirm(request, uidb64=None, token=None):
    print uidb64
    print token
    return password_reset_confirm(request, uidb64=uidb64, token=token)

def getDistanceFromUser(user_lat, user_lng, item_lat, item_lng):
    user = (user_lat, user_lng)
    item = (item_lat, item_lng)

    return vincenty(user, item).miles

class CreateNonFacebookVendorView(APIView):
    permission_classes = (AllowAny,) 
    serializer_class = serializers.UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.DATA)
        user = None

        try:
            user = User.objects.get(email=serializer.init_data['email'])
        except ObjectDoesNotExist:
            print 'No User'

        if user:
            return Response({'email' : 'This email is already associated with a beLocal account.'}, status=status.HTTP_400_BAD_REQUEST)             

        if serializer.is_valid():
            user = User.objects.create_user(
                username=serializer.init_data['username'],
                first_name=serializer.init_data['first_name'],
                last_name=serializer.init_data['last_name'],
                email=serializer.init_data['email'],
                password=serializer.init_data['password']
            )

        if user:
            token, created_token = Token.objects.get_or_create(user=user)
            vendor = Vendor.objects.create(user=user)

            if(not created_token):
                return HttpResponse(status=status.HTTP_304_NOT_MODIFIED)
            
            # If the user is a newly created vendor, make them inactive.
            user.is_staff = 1 # make the user a vendor
            vendor.is_active = False # make the user inactive
            vendor.save()
            user.save()

            vendor.company_name = user.username # set this for Carly's UI

            vp = VendorPhoto(image=File(open('../client/app/images/profilePH.jpg')))
            vp.save()
            vendor.photo = vp

            vendor.save()

            vendor = Vendor.objects.get(user=user)  
                
            vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote       
            response = {}
            response = {'id': user.id, 
                        'is_active' : vendor.is_active, 
                        'name': user.username, 
                        'email' : user.email, 
                        'first_name': user.first_name, 
                        'last_name': user.last_name, 
                        'userType': 'VEN',
                        'vendor' : serializers.VendorSerializer(vendor).data, 
                        'token': token.key
            }
            
            return Response(response)    
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)     

class CreateNonFacebookCustomerView(APIView):
    permission_classes = (AllowAny,) 
    serializer_class = serializers.UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.DATA)
        user = None

        try:
            user = User.objects.get(email=serializer.init_data['email'])
        except ObjectDoesNotExist:
            print 'No User'

        if user:
            return Response({'email' : 'This email is already associated with a beLocal account.'}, status=status.HTTP_400_BAD_REQUEST)   

        if serializer.is_valid():
            user = User.objects.create_user(
                username=serializer.init_data['username'],
                first_name=serializer.init_data['first_name'],
                last_name=serializer.init_data['last_name'],
                email=serializer.init_data['email'],
                password=serializer.init_data['password']
            )

        if user:
            token, created_token = Token.objects.get_or_create(user=user)

            if(not created_token):
                return HttpResponse(status=status.HTTP_304_NOT_MODIFIED)            

            response = {}
            response = {'id': user.id, 'name': user.username, 'email' : user.email, 'first_name': user.first_name, 'last_name': user.last_name, 'userType': 'CUS', 'token': token.key}

            return Response(response)    
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)                            

class LoginView(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer
    model = Token
    vendors_per_page = 20; 
 
    def post(self, request, backend):
        serializer = self.serializer_class(data=request.DATA)
        user = register_by_access_token(request, backend)

        if user:
            token = Token.objects.get(user=user)
            response = {}
            if user.is_staff and not user.is_superuser:
                vendor = Vendor.objects.get(user=user)
                vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote
                response = {'id': user.id, 
                            'is_active' : vendor.is_active, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'VEN', 
                            'vendor' : serializers.VendorSerializer(vendor).data, 
                            'token': token.key
                }
            elif not user.is_superuser:
                response = {'id': user.id, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'CUS', 
                            'token': token.key
                }
            else:
                response = {'id': user.id, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'SUP', 
                            'token': token.key
                }                
            return Response(response)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginNoFBView(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer
 
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.DATA)
        user = None

        if serializer.is_valid():
            user = authenticate(username=request.DATA['username'], password=request.DATA['password'])

        if user:
            token = Token.objects.get(user=user)
            response = {}
            if user.is_staff and not user.is_superuser:
                vendor = Vendor.objects.get(user=user)
                vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote
                response = {'id': user.id, 
                            'is_active' : vendor.is_active, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'VEN', 
                            'vendor' : serializers.VendorSerializer(vendor).data, 
                            'token': token.key
                }
            elif not user.is_superuser:
                response = {'id': user.id, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'CUS', 
                            'token': token.key
                }
            else:
                response = {'id': user.id, 
                            'name': user.username, 
                            'email' : user.email, 
                            'first_name': user.first_name, 
                            'last_name': user.last_name, 
                            'userType': 'SUP', 
                            'token': token.key
                }                
            return Response(response)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)                        

class CreateVendorView(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer
    model = Token
 
    def post(self, request, backend):
        serializer = self.serializer_class(data=request.DATA)
        user = register_by_access_token(request, backend)

        if user:
            token, created_token = Token.objects.get_or_create(user=user)
            vendor = Vendor.objects.get(user=user)

            if(not created_token):
                return HttpResponse(status=status.HTTP_304_NOT_MODIFIED)
            
            # If the user is a newly created vendor, make them inactive.
            user.is_staff = 1 # make the user a vendor
            vendor.is_active = False # make the user inactive
            vendor.save()
            user.save()

            vendor.company_name = user.username # set this for Carly's UI
            vendor.save()
                
            vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote            
            response = {}
            response = {'id': user.id, 
                        'is_active' : vendor.is_active, 
                        'name': user.username, 
                        'email' : user.email, 
                        'first_name': user.first_name, 
                        'last_name': user.last_name, 
                        'userType': 'VEN',
                        'vendor' : serializers.VendorSerializer(vendor).data, 
                        'token': token.key
            }
            
            return Response(response)    
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CreateCustomerView(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer
    model = Token
 
    def post(self, request, backend):
        serializer = self.serializer_class(data=request.DATA)
        user = register_by_access_token(request, backend)

        if user:
            token, created_token = Token.objects.get_or_create(user=user)

            if(not created_token):
                return HttpResponse(status=status.HTTP_304_NOT_MODIFIED)            

            response = {}
            response = {'id': user.id, 'name': user.username, 'email' : user.email, 'first_name': user.first_name, 'last_name': user.last_name, 'userType': 'CUS', 'token': token.key}

            return Response(response)    
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)                               

@psa()
def register_by_access_token(request, backend):
    backend = request.backend
    # Split by spaces and get the array
    auth = get_authorization_header(request).split()
 
    if not auth or auth[0].lower() != 'token':
        msg = 'No token header provided.'
        return msg
 
    if len(auth) == 1:
        msg = 'Invalid token header. No credentials provided.'
        return msg
 
    access_token = auth[1]
 
    user = backend.do_auth(access_token)

    return user

class MarketDetailsView(generics.CreateAPIView):
    permission_classes = (AllowAny,)   

    def post(self, request, *args, **kwargs):
        market = Market.objects.get(pk=request.DATA["id"])

        if(market != None):
            market.is_liked = Market.objects.from_request(self.request).get(pk=market.id).user_vote
            return Response(serializers.MarketDetailsSerializer(market).data, status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class VendorDetailsView(generics.CreateAPIView):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(pk=request.DATA["id"])
        if(vendor.is_active == True):
            locations = SellerLocation.objects.filter(vendor=vendor)
            products = Product.objects.filter(vendor=vendor, stock="IS")
            markets = Market.objects.filter(vendors=vendor)
            vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote

            if products is not None:
                for product in products:
                    product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote 

            if markets is not None:
                for market in markets:
                    market.is_liked = Market.objects.from_request(self.request).get(pk=market.id).user_vote                    

            return Response({"vendor":serializers.VendorSerializer(vendor).data, 
                             "selling_locations":serializers.SellerLocationSerializer(locations, many=True).data,
                             "markets":serializers.MarketDisplaySerializer(markets, many=True).data,
                             "products":serializers.ProductDisplaySerializer(products, many=True).data
                            }, 
                            status=status.HTTP_200_OK
            )  
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class AddVendorView(generics.CreateAPIView):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.VendorSerializer(data=request.DATA)

        if serializer.is_valid():
            user = User.objects.get(id=serializer.init_data['user'])
            user.is_staff = 1 # make the user a vendor
            user.save()

            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)   
        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)

class RWDVendorView(generics.RetrieveUpdateDestroyAPIView):
    """
    This view  provides an endpoint for Sellers to view and
    modify their information
    """
    
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 
    serializer_class = serializers.VendorSerializer

    def get(self, request):
        vendor = Vendor.objects.get(user=request.user)
        
        if vendor is not None:
            vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote
            serializer = serializers.VendorSerializer(vendor)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_404_NOT_FOUND)

    #Do we want to have a vendor delete here?
    def delete(self, request):
        vendor = Vendor.objects.get(user=request.user)

        if vendor is not None:
            user = User.objects.get(id=serializer.init_data['user'])
            user.is_staff = 0
            user.save()
            vendor.delete()
            return Response("Success", status=status.HTTP_204_NO_CONTENT)
        else:
            return Response("Vendor not found", status=status.HTTP_404_NOT_FOUND)

    def patch(self, request):
        vendor = Vendor.objects.get(user=request.user) 
   
        if vendor is not None:
            print request.DATA.keys()
            serializer = serializers.EditVendorSerializer(vendor, data=request.DATA, partial=True)
           
            if serializer.is_valid():
                serializer.save()

                d = serializer.data
                p = VendorPhoto.objects.get(pk=serializer.data["photo"])
                serializer.data["photo"] = serializers.VendorPhotoPathSerializer(p).data

                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 
        else:
            return Response("Vendor not found", status=status.HTTP_404_NOT_FOUND) 

    def get_object(self):
        try:
            vendor = Vendor.objects.get(user=self.request.user)
        except vendor.DoesNotExist:
            raise Http404
        return vendor

class AddProductView(generics.CreateAPIView):
    """
    This view provides an endpoint for sellers to
    add a product to their products list.
    """         
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)   
    serializer_class = serializers.AddProductSerializer  


    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(user=request.user)
        request.DATA['vendor'] = vendor.id

        serializer = serializers.AddProductSerializer(data=request.DATA, partial=True)
       
        if serializer.is_valid():
            current_product = serializer.save()

            if (current_product.photo == None): 
                pp = ProductPhoto(image=File(open('../client/app/images/productPH.png')))
                pp.save()
                current_product.photo = pp  
                current_product = serializer.save()     

            # Save tags if they are provided in the request.
            if type(serializer.data['tags']) is list:                
                saved_product = Product.objects.get(pk=current_product.pk)
                saved_product.tags.clear()
                for tag in serializer.data['tags']:
                    saved_product.tags.add(tag)
            
            return Response(status=status.HTTP_201_CREATED)

        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)
    

class RWDProductView(generics.RetrieveUpdateDestroyAPIView):
    """
    This view provides an endpoint for sellers to
    read-write-delete a product from their products list.
    """   
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 
    serializer_class = serializers.ProductSerializer
    
    def get(self, request, product_id):       
        product = Product.objects.get(pk=product_id)
        product.is_liked = Product.objects.from_request(request).get(pk=product.id).user_vote
        
        if product is not None:
            serializer = serializers.ProductDisplaySerializer(product) 
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response("Product not found", status=status.HTTP_404_NOT_FOUND)  
    
    def delete(self, request, product_id):       
        product = Product.objects.get(pk=product_id)
        
        if product is not None:
            product.delete() 
            return Response("Success", status=status.HTTP_204_NO_CONTENT)
        else:
            return Response("Product not found", status=status.HTTP_404_NOT_FOUND)                  
    
    def patch(self, request, product_id):         
        product = Product.objects.get(pk=product_id) 
        
        if product is not None:
            serializer = serializers.AddProductSerializer(product, data=request.DATA, partial=True)
           
            if serializer.is_valid():
                curr = serializer.save()
                print "saved:", curr, curr.category
                # Save tags if they are provided in the request.
                if type(serializer.data['tags']) is list:                
                    saved_product = Product.objects.get(pk=product_id)
                    saved_product.tags.clear()
                    for tag in serializer.data['tags']:
                        saved_product.tags.add(tag)

                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 
        else:
            return Response("Product not found", status=status.HTTP_404_NOT_FOUND) 

class RWDSellerLocationView(generics.RetrieveUpdateAPIView):
    """
    This view provides an endpoint for deleting and modifying seller locations         
    """
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.SellerLocationSerializer

    def patch(self, request, location_id):

        # Workaround for a Django bug that doesn't allow for multiple nested objects to be deserialized properly
        # As a result, we need to clear out the hours for recurring events and re-add them each time
        if(request.method == 'PATCH'):
            location = SellerLocation.objects.get(pk=location_id)
            address = location.address
            address.date = None
            address.save()
            hours = OpeningHours.objects.filter(address=address)
            for hour in hours:
                hour.delete()

        self.id = location_id
        return self.partial_update(request)

    def get_object(self):
        try:
            location = SellerLocation.objects.get(pk = self.id)  
        except location.DoesNotExist:
            raise Http404
        return location

class DeleteSellerLocationView(generics.CreateAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 

    def post(self, request):
        if("id" in request.DATA.keys() and "action" in request.DATA.keys()):
            if(request.DATA["action"] == "restore"):
                location = SellerLocation.trash.get(pk=request.DATA["id"])

                if location is not None:
                    location.restore()
                    return Response("Restored location", status=status.HTTP_204_NO_CONTENT)
                else:
                    return Response("Location not found for restore", status=status.HTTP_400_BAD_REQUEST)                    
            elif(request.DATA["action"] == "trash"):
                location = SellerLocation.objects.get(pk=request.DATA["id"])

                if location is not None:
                    location.delete()
                    return Response("Trashed location", status=status.HTTP_204_NO_CONTENT)
                else:
                    return Response("Location not found for trashing", status=status.HTTP_400_BAD_REQUEST) 
        else:
            return Response("id not provided", status=status.HTTP_400_BAD_REQUEST)

class DeleteProductView(generics.CreateAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 
    
    def post(self, request):
        if("id" in request.DATA.keys() and "action" in request.DATA.keys()):
            if(request.DATA["action"] == "restore"):
                product = Product.trash.get(pk=request.DATA["id"])

                if product is not None:
                    product.restore()
                    return Response("Restored product", status=status.HTTP_204_NO_CONTENT)
                else:
                    return Response("Product not found for restore", status=status.HTTP_400_BAD_REQUEST)                    
            elif(request.DATA["action"] == "trash"):
                product = Product.objects.get(pk=request.DATA["id"])

                if product is not None:
                    product.delete()
                    return Response("Trashed product", status=status.HTTP_204_NO_CONTENT)
                else:
                    return Response("Product not found for trashing", status=status.HTTP_400_BAD_REQUEST) 
        else:
            return Response("id not provided", status=status.HTTP_400_BAD_REQUEST)               

class AddProductPhotoView(generics.CreateAPIView):
    """
    This view provides an endpoint to save product photo. 
    """
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 
    serializer_class = serializers.ProductPhotoSerializer
    model = ProductPhoto

class AddVendorPhotoView(generics.CreateAPIView):
    """
    This view provides an endpoint to save vendor photo.
    """
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,) 
    serializer_class = serializers.VendorPhotoSerializer
    model = VendorPhoto
    
class RWDProductPhotoView(generics.RetrieveUpdateDestroyAPIView):
    """
    This view provides an endpoint for sellers to
    read-write-delete a product's image.
    """  
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    
    serializer_class = serializers.ProductPhotoSerializer
    model = ProductPhoto  
            
class VendorProductView(generics.ListAPIView):
    """
    This view provides an endpoint for vendors to view their products.
    """   
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.ProductDisplaySerializer

    def get_queryset(self):
        vendor = Vendor.objects.get(user=self.request.user)
        products = Product.objects.filter(vendor=vendor)

        if products is not None:
            for product in products:
                product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote
            
            return products
        else:
            return Response(status=status.HTTP_404_NOT_FOUND) 

class UpdateStockView(generics.CreateAPIView):
    """
    This view provides an endpoint for vendors to view their products.
    """   
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.ProductSerializer

    def post(self, request):
        error = '{"error":"Required attributes not provided"}'
        if "product_id" in request.DATA and "value" in request.DATA:
            product = Product.objects.get(pk=request.DATA["product_id"])
            error = '{"error":"Provided data is invalid"}'
            if(product != None):
                if(request.DATA["value"] == "IS"):
                    product.stock = Product.IN_STOCK
                elif(request.DATA["value"] == "OOS"):
                    product.stock = Product.OUT_OF_STOCK
                product.save()
                return Response(status=status.HTTP_200_OK)            
        return Response(data=error, status=status.HTTP_400_BAD_REQUEST)

#TODO: Currenty this view simply returns all products rather
# than trending ones
class TrendingProductView(generics.ListAPIView):
    """
    This view provides an endpoint for customers to
    view currently trending products.
    """   
    permission_classes = (AllowAny,)
    serializer_class = serializers.ProductDisplaySerializer
    
    def post(self, request):
        """ 
        if ('user_position' in request.DATA.keys() and request.DATA['user_position'] is not None):
            lat, lng = map(float, request.DATA['user_position'].strip('()').split(','))

            locations = SellerLocation.objects.filter(vendor__is_active=True)

            for location in locations: 
                location.sortkey = getDistanceFromUser(lat, lng, location.address.latitude, location.address.longitude)

            locations = sorted(locations, key=attrgetter('sortkey'))

            products = []
            vendors = [] 

            #Go through all locations sorted by proximity
            for location in locations:
                if(location.vendor not in vendors): #To make sure we don't add the same item from two diff. locations
                    vendors.append(location.vendor)
                    products.extend(Product.objects.filter(vendor=location.vendor, stock=Product.IN_STOCK))

            if products is not None:
                for product in products:
                    product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote                    
            
            serializer = serializers.ProductDisplaySerializer(products, many=True) 
            return Response(serializer.data)

        else:
            
            products = Product.objects.filter(stock=Product.IN_STOCK).filter(vendor__is_active=True)
            if products is not None:
                for product in products:
                    product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote
            serializer = serializers.ProductDisplaySerializer(products, many=True)
           
            return Response(serializer.data)
        """
        products = Product.objects.filter(stock=Product.IN_STOCK).filter(vendor__is_active=True).order_by('?')
        if products is not None:
            for product in products:
                product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote
        serializer = serializers.ProductDisplaySerializer(products, many=True)

        return Response(serializer.data)

class ListMarketsView(generics.ListAPIView):
    """
    this view provides an endpoint for customers to 
    view current markets
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.MarketDisplaySerializer

    def get_queryset(self):
        markets = Market.objects.all()
        if markets is not None:
            for market in markets:
                market.is_liked = Market.objects.from_request(self.request).get(pk=market.id).user_vote
        
        return markets


class MarketView(generics.ListAPIView):
    """
    This view provides an endpoint for customers to check the available 
    Seller locations for the given market id
    """

    permission_classes = (AllowAny,)
    serializer_class = serializers.AddSellerLocationSerializer

    def get_queryset(self):
        market_id = self.kwargs['market_id']
        market_address = Address.objects.get(pk=market_id)

        return SellerLocation.objects.filter(address = market_address)

class VendorsView(generics.ListAPIView):
    """
    This view provides an endpoint for customers to view
    vendors.
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.VendorTabSerializer

    def get_queryset(self):
        vendors = Vendor.objects.filter(is_active=True)
        if vendors is not None:
            for vendor in vendors:
                vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote 
                
        return vendors

    def post(self, request):
        if ('user_position' in request.DATA.keys() and request.DATA['user_position'] is not None):

            lat, lng = map(float, request.DATA['user_position'].strip('()').split(','))

            locations = SellerLocation.objects.filter(vendor__is_active=True)

            #Sort locations based on proximity to current user
            for location in locations: 
                location.sortkey = getDistanceFromUser(lat, lng, location.address.latitude, location.address.longitude)

            locations = sorted(locations, key=attrgetter('sortkey'))

            vendors = []

            #Fill vendor queryset with order based on their closest locations
            for location in locations: 
                if(location.vendor not in vendors):
                    vendor = Vendor.objects.get(pk=location.vendor.id)
                    vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote 
                    vendors.append(vendor)
                    
            serializer = serializers.VendorTabSerializer(vendors, many=True)
            return Response(serializer.data)

        else: 
            vendors = Vendor.objects.filter(is_active=True)
            
            if vendors is not None:
                for vendor in vendors:
                    vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote
            
            serializer = serializers.VendorTabSerializer(vendors, many=True)
            return Response(serializer.data)

class ListVendorLocations(generics.ListAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    serializer_class = serializers.SellerLocationSerializer

    def get_queryset(self):
        vendor = Vendor.objects.get(user=self.request.user)

        return SellerLocation.objects.filter(vendor=vendor)

class ListVendorMarkets(generics.ListAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    serializer_class = serializers.VendorMarketDisplaySerializer

    def get_queryset(self):
        vendor = Vendor.objects.get(user=self.request.user)

        return Market.objects.filter(vendors=vendor) 

class ListAvailableVendorMarkets(generics.ListAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    serializer_class = serializers.VendorMarketDisplaySerializer

    def get_queryset(self):
        vendor = Vendor.objects.get(user=self.request.user)

        return Market.objects.exclude(vendors=vendor)              

class JoinMarketView(generics.CreateAPIView):

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(user=request.user)

        market = Market.objects.get(pk=request.DATA['market_id'])
        market.vendors.add(vendor)
        market.save()

        return HttpResponse(status=status.HTTP_200_OK)

class LeaveMarketView(generics.CreateAPIView):

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(user=request.user)

        market = Market.objects.get(pk=request.DATA['market_id'])
        market.vendors.remove(vendor)
        market.save()

        return HttpResponse(status=status.HTTP_200_OK)        

class AddSellerLocationView(generics.CreateAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(user=request.user)
        request.DATA['vendor'] = vendor.id       

        serializer = serializers.SellerLocationSerializer(data=request.DATA, many=False)

        if serializer.is_valid(): 
            current_location = serializer.save()
            address = current_location.address.id;             

            return HttpResponse(status=status.HTTP_201_CREATED)

        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)  

class JsonHelper(sjson.JSONEncoder):
     """ simplejson.JSONEncoder extension: handle Search view models"""
     def default(self, obj):
        return obj.__dict__

class autocompleteViewModel():
    def __init__(self, name):
        self.name = name

def autocomplete(request):
    products = []
    prodSqs = SearchQuerySet().models(Product).autocomplete(name_auto=request.GET.get('q', ''))
    for product in [result.object for result in prodSqs]:
        if product is not None and product.vendor.is_active:
            products.append(autocompleteViewModel(product.name))
    the_data = sjson.dumps({
        'products': products}, cls=JsonHelper)
    return HttpResponse(the_data, content_type='application/json')

class SearchProductView(generics.ListAPIView):
    serializer_class = serializers.ProductDisplaySerializer

    def get_queryset(self):
        srch = self.request.GET.get('q', '')
        sqs = SearchQuerySet().models(Product) #.filter(has_title=True)
        clean_query = sqs.query.clean(srch)
        results = sqs.filter(content=clean_query)

        products = []

        for product in [result.object for result in results]:
            if product is not None:
                product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote
                products.append(product)      
        
        return products

class SearchVendorView(generics.ListAPIView):
    serializer_class = serializers.CustomerVendorSerializer

    def get_queryset(self):
        srch = self.request.GET.get('q', '')
        sqs = SearchQuerySet().models(Vendor)
        company = sqs.filter(company_name=srch)
        phone = sqs.filter(phone=srch)
        webpage = sqs.filter(webpage=srch)
        city = sqs.filter(city=srch)
        state = sqs.filter(state=srch)
        zipcode = sqs.filter(zipcode=srch)
        addr = sqs.filter(addr_line1=srch)
        country = sqs.filter(country=srch)
        country_code = sqs.filter(country_code=srch)

        results = company | phone | webpage | city | state | zipcode | addr | country | country_code
        
        vendors = []

        for vendor in [result.object for result in results]:
            if vendor is not None:
                vendor.is_liked = Vendor.objects.from_request(self.request).get(pk=vendor.id).user_vote
                vendors.append(vendor)
        
        return vendors

class SearchMarketView(generics.ListAPIView):
    serializer_class = serializers.MarketSearchSerializer

    def get_queryset(self):
        srch = self.request.GET.get('q', '')
        sqs = SearchQuerySet().models(Market)
        name = sqs.filter(name=srch)
        webpage = sqs.filter(webpage=srch)
        city = sqs.filter(city=srch)
        state = sqs.filter(state=srch)
        zipcode = sqs.filter(zipcode=srch)
        addr = sqs.filter(addr_line1=srch)
        country = sqs.filter(country=srch)

        results = name | webpage | city | state | zipcode | addr | country
        
        markets = []

        for market in [result.object for result in results]:
            markets.append(market)      
        
        return markets

@csrf_exempt
def like(request, content_type, id):
    """ 
    Handles likes on a model object.
    """
    # check the content_type
    if isinstance(content_type, ContentType):
        pass
    elif isinstance(content_type, ModelBase):
        content_type = ContentType.objects.get_for_model(content_type)
    elif isinstance(content_type, basestring) and '-' in content_type:
        app, modelname = content_type.split('-')
        content_type = ContentType.objects.get(app_label=app, model__iexact=modelname)
    else:
        content_type = ContentType.objects.get(app_label='be_local_server', model__iexact=content_type)

    if request.method == 'POST':
        response = views.vote(
                              request,
                              content_type = content_type,
                              object_id = id,
                              vote = '+1',
                              mimetype='application/json'
        )
        
        # JSON formatting
        response.content = response.content.replace("'","\"")
        return response 
    
    if request.method == 'DELETE':
        response = views.vote(
                              request,
                              content_type = content_type,
                              object_id = id,
                              vote=None,
                              mimetype='application/json'
        )
        
        # JSON formatting
        response.content = response.content.replace("'","\"")
        return response
    
    if request.method == 'GET':
        vote = content_type.model_class().objects.from_request(request).get(pk=id).user_vote
        if (vote):
            body = '{"is_liked": true}'
            return HttpResponse(body, status=status.HTTP_200_OK, content_type='application/json')
        else:
            body = '{"is_liked": false}'
            return HttpResponse(body, status=status.HTTP_404_NOT_FOUND, content_type='application/json') 
        
class ListProductTags(generics.ListAPIView):
    """ 
    This view provides an endpoint to list available tags.
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.TagSerializer

    def get_queryset(self):
        return Tag.objects.all()

class ManageVendorsView(generics.ListAPIView):
    """ 
    This view provides an endpoint to list available tags.
    """
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.ManageVendorSerializer    

    def get_queryset(self):
        return Vendor.objects.filter(user__is_staff=True)

class ManageUsersView(generics.ListAPIView):
    """ 
    This view provides an endpoint to list available tags.
    """
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.ManageUserSerializer    

    def get_queryset(self):
        return User.objects.all()

class ActivateVendorView(generics.CreateAPIView):

    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        vendor = Vendor.objects.get(pk=request.DATA["id"])
        vendor.is_active = not vendor.is_active
        vendor.save()

        return HttpResponse(status=status.HTTP_200_OK)        

class TaggedProductView(generics.ListAPIView):
    """ 
    This view provides an endpoint to list products having a given tag.
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.ProductDisplaySerializer

    def get_queryset(self):
        products = Product.objects.filter(tags__slug=self.kwargs.get('tag_slug')).filter(stock=Product.IN_STOCK).filter(vendor__is_active=True)
       
        if products is not None:
            for product in products:
                product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote 
        
        return products
       
class ListProductCategories(generics.ListAPIView):
    """ 
    This view provides an endpoint to list available categories.
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.CategorySerializer

    def get_queryset(self):
        return Category.objects.all() 

class CategorizedProductView(generics.ListAPIView):
    """ 
    This view provides an endpoint to list products of a given cateogry.
    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.ProductDisplaySerializer

    def get_queryset(self):
        products = Product.objects.filter(category__slug=self.kwargs.get('category_slug')).filter(stock=Product.IN_STOCK).filter(vendor__is_active=True)
       
        if products is not None:
            for product in products:
                product.is_liked = Product.objects.from_request(self.request).get(pk=product.id).user_vote 
        
        return products   

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import csv
import time
import pandas as pd
import numpy as np
from itertools import chain
import re

PATH = 'C:\Program Files (x86)\chromedriver.exe'
STATE = 'ga' # Can be city-state (atlanta-ga)
URL = 'https://www.apartments.com/apartments/' + STATE + '/'
driver = webdriver.Chrome(PATH)
wait = WebDriverWait(driver, 10)

# Scraping functions:
# How to collect links of apartments
def get_links(url):
    driver.get(url)
    container = wait.until(EC.presence_of_element_located((By.ID, 'placardContainer')))
    wrappers = container.find_elements_by_class_name('mortar-wrapper')
    links = []
    for w in wrappers:
        status = w.find_element_by_class_name('availability').text
        if status != 'Unavailable':
            link = w.find_element_by_class_name('property-link').get_attribute('href')
        else:
            continue
        links.append(link)
    return links
  
def get_aprtment_links(url):
    print('Start collecting apartment links...')
    driver.get(url)
    container = wait.until(EC.presence_of_element_located((By.ID, 'placardContainer')))
    try:
        # Find the last page and store in a list
        page_range = container.find_element_by_class_name('pageRange').text
        last_page = int(re.search(r'\d+$', page_range).group(0))
        pages = [url + str(i) for i in range(1, last_page + 1)]
        print('Collecting from {} pages of apartments...'.format(last_page))
        apartment_links = []
        for p in pages:
            apartment_links.append(get_links(p))
        apartment_links = list(chain.from_iterable(apartment_links))
    except NoSuchElementException:
        print('There is only one page of apartments. Collecting...')
        apartment_links = get_links(url)
    print('{} apartment link(s) collected successfully.'.format(len(apartment_links)))
    print('-----------------------------------')
    return apartment_links

# How to get data of geolocation, name, address,
# phone, unique id, rating, description, and number of rentals
def get_apartment_general_info(soup):
    apt_latitude = soup.find('meta',  property= 'place:location:latitude').attrs['content']
    apt_longtitude = soup.find('meta',  property= 'place:location:longitude').attrs['content']
    apt_name = soup.find('h1', class_= 'propertyName').text.strip()
    find_address = soup.find('div', class_= 'propertyAddress').find_all('span')
    apt_street = find_address[0].text
    apt_city = find_address[1].text
    apt_state = find_address[2].text
    apt_zip = find_address[3].text
    apt_phone = soup.find(class_= 'phoneNumber').text.strip()
    apt_id = soup.find('main').attrs['data-listingid']
    apt_avg_review = soup.find('div', class_= 'rating hasReviews')
    apt_num_reviews = soup.find('a', class_= 'reviewCount')
    if apt_avg_review == None:
        apt_avg_review = np.nan
        apt_num_reviews = np.nan
    else:
        apt_avg_review = apt_avg_review.span.attrs['content']
        apt_num_reviews = re.search(r'\d+', apt_num_reviews.text).group(0)
    apt_description = soup.find('section', id= 'descriptionSection')
    if apt_description == None:
        apt_description == np.nan
    else:
        apt_description = repr(apt_description.p.text).replace(r'\n', '')
    multi_unit = soup.find('table', class_= 'availabilityTable multiunit multifamily')
    if multi_unit != None:
        apt_num_rentals = len(multi_unit.select("tr[class*= 'rentalGridRow']"))
    else:
        apt_num_rentals = 1
    return [apt_id, apt_name, apt_street, apt_city, apt_state, apt_zip,
            apt_phone, apt_num_rentals, apt_num_reviews, apt_avg_review,
            apt_latitude, apt_longtitude, apt_description]

# How to get data of each rental: unique id, number of beds,
# number of baths, monthly rent, surface area, and status
def get_rental_details(rental):
    num_beds = rental.attrs['data-beds']
    num_baths = rental.attrs['data-baths']
    rental_id = rental.attrs['data-rentalkey']
    monthly_rent = rental.find('td', class_= 'rent').text.strip('\n ')
    surface = rental.find('td', class_= 'sqft').text.strip('\n ')
    status = rental.find('td', class_='available').text.strip('\n ')
    rental_details = [rental_id, num_beds, num_baths,
                      surface, monthly_rent, status]
    return rental_details

def get_apartment_rentals(soup):
    apt_id = soup.find('main').attrs['data-listingid']
    multi_unit = soup.select("table[class*= 'availabilityTable multiuni']")
    if multi_unit != []:
        rental_containers = soup.find('div', class_= 'tabContent active').select("tr[class*= 'rentalGridRow']")
        apt_rentals = []
        for r in rental_containers:
            apt_rentals.append(get_rental_details(r))
        for i in apt_rentals:
            i.insert(0, apt_id)
    else:
        rental_containers = soup.select_one("table[class*= 'availabilityTable']").select_one("tr[class*= 'rentalGridRow']")
        apt_rentals = get_rental_details(rental_containers)
        apt_rentals.insert(0, apt_id)
        apt_rentals = [apt_rentals]
    return apt_rentals

# How to get data of expenses: type, name, and amount
def get_expenses_details(expense_description):
    expense_type = expense_description.find('h3').text
    expense_containers = expense_description.find_all('div', class_= 'descriptionWrapper')
    expense_details = []
    for e in expense_containers:
        expense_name = e.find_all('span')[0].text
        expense_amount = e.find_all('span')[1].text
        expense_details.append([expense_type, expense_name, expense_amount])
    return expense_details

def get_apartment_expenses(soup):
    apt_id = soup.find('main').attrs['data-listingid']
    expenses = soup.find('div', id= 'feesWrapper')
    if expenses == None:
        apt_expenses = ''
    else:
        expense_description = expenses.find_all('div', class_= lambda x: x != 'descriptionWrapper')
        apt_expenses = [get_expenses_details(e) for e in expense_description]
        apt_expenses = list(chain.from_iterable(apt_expenses))
        for i in apt_expenses:
            i.insert(0, apt_id)
    return apt_expenses

# How to get amenity data: name and details
def get_apartment_amenities(soup):
    apt_id = soup.find('main').attrs['data-listingid']
    amenities = soup.find('section', id= 'amenitiesSection')
    apt_amenities = []
    if amenities == None:
        apt_amenities = ''
    else:
        amenity_description = amenities.select("div[class*= 'specList']")
        for a in amenity_description:
            clean_amenity = list(map(str.strip, repr(a.text.replace('•', '')).split(r'\n')))
            amenity_name = clean_amenity[1]
            amenity_details = [i for i in clean_amenity[2:] if i.strip("' ")]
            apt_amenities.append([apt_id, amenity_name, amenity_details])
    return apt_amenities

# How to get data of nearby places:
# type, name, distance from the aprtment
def get_apartment_nearby_places(soup):
    apt_id = soup.find('main').attrs['data-listingid']
    places = soup.find_all('div', class_= 'transportationDetail')
    apt_nearby_places = []
    for p in places:
        place_type = p.find('thead', class_= 'longLabel').th.text.strip()
        place_description = p.tbody.find_all('tr')
        for i in place_description:
            place_name = i.find_all('td')[0].text.strip()
            place_distance = re.search(r'\d+\.\d+', i.find_all('td')[2].text).group(0)
            apt_nearby_places.append([apt_id, place_type, place_name, place_distance])
    return apt_nearby_places

# Apply functions and scrape data
apartment_links = get_aprtment_links(URL)
time.sleep(2)
print('Start scraping...')
apt_general_info = []
apt_rentals = []
apt_expenses = []
apt_amenities = []
apt_nearby_places = []
count = 0
for link in apartment_links:
    count += 1
    print(f'Apartment number {count}. Collecting...')
    driver.get(link)
    time.sleep(5)
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')
    apt_general_info.append(get_apartment_general_info(soup))
    apt_rentals.append(get_apartment_rentals(soup))
    apt_expenses.append(get_apartment_expenses(soup))
    apt_amenities.append(get_apartment_amenities(soup))
    apt_nearby_places.append(get_apartment_nearby_places(soup))
    print('Successfully.')
    print('-----------------------------------')
apt_rentals = list(chain.from_iterable(apt_rentals))
apt_expenses = list(chain.from_iterable(apt_expenses))
apt_amenities = list(chain.from_iterable(apt_amenities))
apt_nearby_places = list(chain.from_iterable(apt_nearby_places))
driver.close()

# Writing data files
print('-----------------------------------')
print('Start writing files...')
print('Writing apartment_info file...')
with open('apartment_info.csv', 'w', newline= '') as f:
    writer = csv.writer(f)
    writer.writerow(['apt_id', 'apt_name', 'apt_street', 'apt_city', 'apt_state', 'apt_zip',
                     'apt_phone', 'apt_num_rentals', 'apt_num_reviews', 'apt_avg_review',
                     'apt_latitude', 'apt_longtitude', 'apt_description'])
    for row in apt_general_info:
        writer.writerow(row)

print('Writing rentals file...')
with open('rentals.csv', 'w', newline= '') as f:
    writer = csv.writer(f)
    writer.writerow(['apt_id', 'rental_id', 'num_beds', 'num_baths',
                     'surface', 'monthly_rent', 'status'])
    for row in apt_rentals:
        writer.writerow(row)

print('Writing expenses file...')
with open('expenses.csv', 'w', newline= '') as f:
    writer = csv.writer(f)
    writer.writerow(['apt_id', 'expense_type', 'expense_name', 'expense_amount'])
    for row in apt_expenses:
        writer.writerow(row)

print('Writing amenities file...')
with open('amenities.csv', 'w', newline= '') as f:
    writer = csv.writer(f)
    writer.writerow(['apt_id', 'amenity_name', 'amenity_description'])
    for row in apt_amenities:
        writer.writerow(row)

print('Writing nearby_places file...')
with open('nearby_places.csv', 'w', newline= '') as f:
    writer = csv.writer(f)
    writer.writerow(['apt_id', 'place_type', 'place_name', 'place_distance'])
    for row in apt_nearby_places:
        writer.writerow(row)

print('All files written successfully!')

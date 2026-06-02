# dropdown_data.py

DROPDOWN_OPTIONS = {
    "Gender": {
        "options": ["male", "female"],
        "visible": 2
    },
    "Marital status": {
        "options": ["Never married", "Divorced", "Awaiting Divorce", "widowed"],
        "visible": 4
    },
    "State": {
        "options": [
            "Andaman & Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
            "Chattisgarh","Dadra Nagar Haveli","Daman &Diu","Delhi","Goa","Gujarat","Haryana",
            "Himachal Pradesh","Jammu & Kashmir","Jharkhand","Karnataka","Kerala","Lakshadweep",
            "Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland","Odisha",
            "Pondicherry","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura",
            "Uttar Pradesh","Uttarakhand","West Bengal"
        ],
        "visible": 8
    },
    "District": {
        "options": [
            "Adilabad","Agra","Ahmed Nagar","Ahmedabad","Aizawl","Ajmer","Akola","Alappuzha","Aligarh","Alirajpur",
            "Allahabad","Almora","Alwar","Ambala","Ambedkar Nagar","Amravati","Amreli","Amritsar","Anand",
            "Ananthapur","Ananthnag","Angul","Anuppur","Ariyalur","Arwal","Ashok Nagar","Auraiya","Aurangabad",
            "Azamgarh","Bagalkot","Bageshwar","Bagpat","Bahraich","Balaghat","Balangir","Baleswar","Ballia",
            "Balrampur","Banaskantha","Banda","Bandipur","Bangalore","Bangalore Rural","Banka","Bankura","Banswara",
            "Barabanki","Baramulla","Baran","Bardhaman","Bareilly","Bargarh","Barmer","Barnala","Barpeta","Barwani",
            "Bastar","Basti","Bathinda","Beed","Begusarai","Belgaum","Bellary","Betul","Bhadrak","Bhagalpur",
            "Bhandara","Bharatpur","Bharuch","Bhavnagar","Bhilwara","Bhind","Bhiwani","Bhojpur","Bhopal","Bidar",
            "Bijnor","Bikaner","Birbhum","Bishnupur","Bokaro","Bongaigaon","Boudh","Budaun","Budgam","Bulandshahr",
            "Buldhana","Bundi","Burhanpur","Buxar","Cachar","Central Delhi","Chamoli","Champawat","Champhai",
            "Chamrajnagar","Chandauli","Chandel","Chandigarh","Chandrapur","Changlang","Chatra","Chennai","Chhatarpur",
            "Chhindwara","Chickmagalur","Chikkaballapur","Chitradurga","Chitrakoot","Chittor","Chittorgarh",
            "Churachandpur","Churu","Coimbatore","Cooch Behar","Cuddalore","Cuddapah","Cuttack","Dadra Nagar Haveli",
            "Dahod","Dakshina Kannada","Damoh","Dantewada","Darbhanga","Darjiling","Darrang","Datia","Dausa",
            "Davangere","Debagarh","Dehradun","Deoghar","Deoria","Dewas","Dhalai","Dhamtari","Dhanbad","Dhar",
            "Dharmapuri","Dharwad","Dhemaji","Dhenkanal","Dholpur","Dhubri","Dhule","Dibang Valley","Dibrugarh",
            "Dimapur","Dindigul","Dindori","Diu","Doda","Dumka","Dungarpur","Durg","East Champaran","East Delhi",
            "East Garo Hills","East Godavari","East Kameng","East Khasi Hills","East Midnapore","East Nimar",
            "East Siang","East Sikkim","East Singhbhum","Ernakulam","Erode","Etah","Etawah","Faizabad","Faridabad",
            "Faridkot","Farrukhabad","Fatehabad","Fatehgarh Sahib","Fatehpur","Fazilka","Firozabad","Firozpur",
            "Gadag","Gadchiroli","Gajapati","Gandhi Nagar","Ganganagar","Ganjam","Garhwa","Gariaband",
            "Gautam Buddha Nagar","Gaya","Ghaziabad","Ghazipur","Giridh","Goalpara","Godda","Golaghat","Gonda",
            "Gondia","Gorakhpur","Gulbarga","Gumla","Guna","Guntur","Gurdaspur","Gurgaon","Gwalior","Hailakandi",
            "Hamirpur","Hanumangarh","Harda","Hardoi","Haridwar","Hassan","Hathras","Haveri","Hazaribag","Hingoli",
            "Hisar","Hooghly","Hoshangabad","Hoshiarpur","Howrah","Hyderabad","Idukki","Imphal East","Imphal West",
            "Indore","Jagatsinghapur","Jaintia Hills","Jaipur","Jaisalmer","Jajapur","Jalandhar","Jalaun",
            "Jalgaon","Jalna","Jalor","Jalpaiguri","Jammu","Jamnagar","Jamtara","Jamui","Janjgir Champa","Jashpur",
            "Jaunpur","Jehanabad","Jhabua","Jhajjar","Jhalawar","Jhansi","Jharsuguda","Jhunjhunu","Jind","Jodhpur",
            "Jorhat","Junagadh","Jyotiba Phule Nagar","Kachchh","Kaithal","Kalahandi","Kamrup","Kanchipuram",
            "Kandhamal","Kangra","Kanker","Kannauj","Kannur","Kanpur Dehat","Kanpur Nagar","Kanyakumari","Kapurthala",
            "Karaikal","Karauli","Karbi Anglong","Kargil","Karim Nagar","Karimganj","Karnal","Karur","Kasargod",
            "Kathua","Katni","Kaushambi","Kawardha","Kendrapara","Kendujhar","Khagaria","Khammam","Khandwa",
            "Khargone","Kheda","Kheri","Khorda","Khunti","Kinnaur","Kiphire","Kodagu","Koderma","Kohima","Kokrajhar",
            "Kolar","Kolasib","Kolhapur","Kolkata","Kollam","Koppal","Koraput","Korba","Koriya","Kota","Kottayam",
            "Kozhikode","Krishna","Krishnagiri","Kulgam","Kullu","Kupwara","Kurnool","Kurung Kumey","Kushinagar",
            "Lahul & Spiti","Lakhimpur","Lakhisarai","Lakshadweep","Lalitpur","Latehar","Latur","Lawngtlai","Leh",
            "Lohardaga","Lohit","Longleng","Lower Dibang Valley","Lower Subansiri","Lucknow","Ludhiana","Lunglei",
            "Madhubani","Madurai","Mahabub Nagar","Maharajganj","Mahasamund","Mahe","Mahesana","Mahoba","Mainpuri",
            "Malappuram","Malda","Malkangiri","Mammit","Mandi","Mandla","Mandsaur","Mandya","Mansa","Marigaon",
            "Mathura","Mau","Mayurbhanj","Medak","Medinipur","Meerut","Mirzapur","Moga","Mohali","Mokokchung",
            "Mon","Moradabad","Morena","Muktsar","Mumbai","Munger","Murshidabad","Muzaffarnagar","Muzaffarpur",
            "Mysore","Nabarangapur","Nadia","Nagaon","Nagapattinam","Nagaur","Nagpur","Nainital","Nalanda","Nalbari",
            "Nalgonda","Namakkal","Nanded","Nandurbar","Narayanpur","Narmada","Narsinghpur","Nashik","Navsari",
            "Nawada","Nawanshahr","Nayagarh","Neemuch","Nellore","New Delhi","Nicobar","Nilgiris","Nizamabad",
            "North & Middle Andaman","North Cachar Hills","North Delhi","North Dinajpur","North East Delhi","North Goa",
            "North Sikkim","North Tripura","North West Delhi","Nuapada","Osmanabad","Pakur","Palakkad","Palamau",
            "Pali","Panch Mahals","Panna","Papum Pare","Parbhani","Patan","Pathanamthitta","Pathankot","Patiala",
            "Patna","Pauri Garhwal","Perambalur","Peren","Phek","Pilibhit","Pithoragarh","Pondicherry","Poonch",
            "Porbandar","Prakasam","Pratapgarh","Pudukkottai","Pulwama","Pune","Puri","Puruliya","Raebareli",
            "Raichur","Raigarh","Raipur","Raisen","Rajauri","Rajgarh","Rajkot","Rajnandgaon","Rajsamand","Ramanagar",
            "Ramanathapuram","Ramgarh","Rampur","Ranchi","Ratlam","Ratnagiri","Rayagada","Reasi","Rewa","Ri Bhoi",
            "Rohtas","Ropar","Rudraprayag","Rupnagar","Sabarkantha","Sagar","Saharanpur","Sahibganj","Saiha",
            "Salem","Samastipur","Sambalpur","Sangli","Sangrur","Sant Kabir Nagar","Sant Ravidas Nagar","Satara",
            "Satna","Sawai Madhopur","Sehore","Senapati","Seoni","Seraikela Kharsawan","Serchhip","Shahdol",
            "Shahjahanpur","Shajapur","Sheikhpura","Sheopur","Shimla","Shimoga","Shivpuri","Shopian","Shrawasti",
            "Sibsagar","Siddharthnagar","Sidhi","Sikar","Simdega","Sindhudurg","Singrauli","Sirmaur","Sirohi",
            "Sitamarhi","Sitapur","Sivaganga","Solan","Solapur","Sonapur","Sonbhadra","Sonitpur","South Andaman",
            "South Delhi","South Dinajpur","South Garo Hills","South Goa","South Sikkim","South Tripura","South West Delhi",
            "Srikakulam","Srinagar","Sultanpur","Sundergarh","Supaul","Surat","Surendra Nagar","Surguja","Tamenglong",
            "Tapi","Tarn Taran","Tawang","Tehri Garhwal","Thane","Thanjavur","The Dangs","Theni","Thiruvananthapuram",
            "Thoubal","Thrissur","Tikamgarh","Tinsukia","Tirap","Tiruchirappalli","Tirunelveli","Tiruvallur",
            "Tiruvannamalai","Tiruvarur","Tonk","Tuensang","Tumkur","Tuticorin","Udaipur","Udham Singh Nagar",
            "Udhampur","Udupi","Ujjain","Ukhrul","Umaria","Una","Unnao","Upper Siang","Upper Subansiri",
            "Uttara Kannada","Uttarkashi","Vadodara","Vaishali","Varanasi","Vellore","Vidisha","Villupuram",
            "Virudhunagar","Visakhapatnam","Vizianagaram","Warangal","Wardha","Washim","Wayanad","West Delhi",
            "West Garo Hills","West Godavari","West Kameng","West Khasi Hills","West Midnapore","West Nimar",
            "West Siang","West Sikkim","West Singhbhum","West Tripura","Wokha","Yadgir","Yavatmal","Zunhebotto"
        ],
        "visible": 10
    },
    "House Type": {
        "options": ["Own","Rental","Lease","PG","Room"],
        "visible": 5
    },
    "Mother Tongue": {
        "options": ["Hindi","Bengali","Urdu","Punjabi","Marathi","Telugu","Tamil","Gujarati","Kannada","Odia","Malayalam","Assamese","Santali","Sanskrit","English","Other"],
        "visible": 8
    },
    "Religion": {
        "options": ["Hindu","Muslim","Christian","Sikh","Buddhist","Jain","Other religion"],
        "visible": 7
    },
    "Nakshatra": {
        "options": ["Ashwini","Bharani","Krittika/Karthikai","Rohini","Mrigasira","Ardra/Thiruvathirai",
                    "Punarvasu/Punarpoosam","Pushya/Pusam","Ashlesha/Ayilyam","Magha/Makam",
                    "Purva Phalguni/Pubba/Puram","Uttara Palkuni / Uthram","Hasta/Hastham","Chitta/Chitra",
                    "Swati","Vishakha/Visakam","Anuradha/Anusham","Jyeshta / Kettai","Mula/Moolam",
                    "Purvashada/Pooradam","Uthradam/Uttarashada","Shravana/Thiruvonam",
                    "Dhanishta / Avittam","Satabhisha/Sadayam","Purva Bhadra/Poorattathi",
                    "Uttarabhadra / Uthirattathi","Revati"],
        "visible": 8
    },
    "Rashi": {
        "options": ["Mesha / Aries","Rishaba/Taurus","Mithuna/Gemini","Kataka/Cancer",
                    "Simha/Leo","Kanya/Virgo","Tula/Libra","Vrishchika/Scorpio","Dhanus/Saggitarius",
                    "Makara/Capricorn","Kumbha/Aquarius","Meena/Pisces"],
        "visible": 8
    },
    "Pada": {
        "options": ["1st Pada","2nd Pada","3rd Pada","4th Pada"],
        "visible": 4
    },
    "Health Info": {
        "options": ["No Health Problems","HIV Positive","Diabetes","Low BP","High BP",
                    "Heart Ailments","Other","Not Filled"],
        "visible": 8
    },
    "Any Disability": {
        "options": ["None","Physical Disability"],
        "visible": 2
    },
    "Diet": {
        "options": ["Veg","Non-Veg","Occasionally Non-Veg","Eggetarian","Jain","Vegan"],
        "visible": 6
    },
    "Height": {
    "options": [
        "4.00 / 48 in / 121.9 cm / 1.22 m",
        "4.01 / 49 in / 124.5 cm / 1.24 m",
        "4.02 / 50 in / 127.0 cm / 1.27 m",
        "4.03 / 51 in / 129.5 cm / 1.30 m",
        "4.04 / 52 in / 132.1 cm / 1.32 m",
        "4.05 / 53 in / 134.6 cm / 1.35 m",
        "4.06 / 54 in / 137.2 cm / 1.37 m",
        "4.07 / 55 in / 139.7 cm / 1.40 m",
        "4.08 / 56 in / 142.2 cm / 1.42 m",
        "4.09 / 57 in / 144.8 cm / 1.45 m",
        "4.10 / 58 in / 147.3 cm / 1.47 m",
        "4.11 / 59 in / 149.9 cm / 1.50 m",
        "5.00 / 60 in / 152.4 cm / 1.52 m",
        "5.01 / 61 in / 154.9 cm / 1.55 m",
        "5.02 / 62 in / 157.5 cm / 1.57 m",
        "5.03 / 63 in / 160.0 cm / 1.60 m",
        "5.04 / 64 in / 162.6 cm / 1.63 m",
        "5.05 / 65 in / 165.1 cm / 1.65 m",
        "5.06 / 66 in / 167.6 cm / 1.68 m",
        "5.07 / 67 in / 170.2 cm / 1.70 m",
        "5.08 / 68 in / 172.7 cm / 1.73 m",
        "5.09 / 69 in / 175.3 cm / 1.75 m",
        "5.10 / 70 in / 177.8 cm / 1.78 m",
        "5.11 / 71 in / 180.3 cm / 1.80 m",
        "6.00 / 72 in / 182.9 cm / 1.83 m",
        "6.01 / 73 in / 185.4 cm / 1.85 m",
        "6.02 / 74 in / 188.0 cm / 1.88 m",
        "6.03 / 75 in / 190.5 cm / 1.91 m",
        "6.04 / 76 in / 193.0 cm / 1.93 m",
        "6.05 / 77 in / 195.6 cm / 1.96 m",
        "6.06 / 78 in / 198.1 cm / 1.98 m",
        "6.07 / 79 in / 200.7 cm / 2.01 m",
        "6.08 / 80 in / 203.2 cm / 2.03 m",
        "6.09 / 81 in / 205.7 cm / 2.06 m",
        "6.10 / 82 in / 208.3 cm / 2.08 m",
        "6.11 / 83 in / 210.8 cm / 2.11 m",
        "7.00 / 84 in / 213.4 cm / 2.13 m",
        "7.01 / 85 in / 215.9 cm / 2.16 m",
        "7.02 / 86 in / 218.4 cm / 2.18 m",
        "7.03 / 87 in / 221.0 cm / 2.21 m",
        "7.04 / 88 in / 223.5 cm / 2.24 m",
        "7.05 / 89 in / 226.1 cm / 2.26 m",
        "7.06 / 90 in / 228.6 cm / 2.29 m",
        "7.07 / 91 in / 231.1 cm / 2.31 m",
        "7.08 / 92 in / 233.7 cm / 2.34 m",
        "7.09 / 93 in / 236.2 cm / 2.36 m",
        "7.10 / 94 in / 238.8 cm / 2.39 m",
        "7.11 / 95 in / 241.3 cm / 2.41 m"
    ],
    "visible": 6
},
"Weight":{
    "options":["0 Kgs","31 Kgs","32 Kgs","33 Kgs","34 Kgs","35 Kgs","36 Kgs","37 Kgs","38 Kgs","39 Kgs",
                "40 Kgs","41 Kgs","42 Kgs","43 Kgs","44 Kgs","45 Kgs","46 Kgs","47 Kgs","48 Kgs","49 Kgs",
                "50 Kgs","51 Kgs","52 Kgs","53 Kgs","54 Kgs","55 Kgs","56 Kgs","57 Kgs","58 Kgs","59 Kgs",
                "60 Kgs","61 Kgs","62 Kgs","63 Kgs","64 Kgs","65 Kgs","66 Kgs","67 Kgs","68 Kgs","69 Kgs",
                "70 Kgs","71 Kgs","72 Kgs","73 Kgs","74 Kgs","75 Kgs","76 Kgs","77 Kgs","78 Kgs","79 Kgs",
                "80 Kgs","81 Kgs","82 Kgs","83 Kgs","84 Kgs","85 Kgs","86 Kgs","87 Kgs","88 Kgs","89 Kgs",
                "90 Kgs","91 Kgs","92 Kgs","93 Kgs","94 Kgs","95 Kgs","96 Kgs","97 Kgs","98 Kgs","99 Kgs",
                "100 Kgs","101 Kgs","102 Kgs","103 Kgs","104 Kgs","105 Kgs","106 Kgs","107 Kgs","108 Kgs","109 Kgs",
                "110 Kgs","111 Kgs","112 Kgs","113 Kgs","114 Kgs","115 Kgs","116 Kgs","117 Kgs","118 Kgs","119 Kgs",
                "120 Kgs","121 Kgs","122 Kgs","123 Kgs","124 Kgs","125 Kgs","126 Kgs","127 Kgs","128 Kgs","129 Kgs",
                "130 Kgs","131 Kgs","132 Kgs","133 Kgs","134 Kgs","135 Kgs","136 Kgs","137 Kgs","138 Kgs","139 Kgs",
                "140 Kgs","141 Kgs","142 Kgs","143 Kgs","144 Kgs","145 Kgs","146 Kgs","147 Kgs","148 Kgs","149 Kgs",
                "150 Kgs","151 Kgs","152 Kgs","153 Kgs","154 Kgs","155 Kgs","156 Kgs","157 Kgs","158 Kgs","159 Kgs",
                "160 Kgs","161 Kgs","162 Kgs","163 Kgs","164 Kgs","165 Kgs","166 Kgs","167 Kgs","168 Kgs","169 Kgs",
                "170 Kgs","171 Kgs","172 Kgs","173 Kgs","174 Kgs","175 Kgs","176 Kgs","177 Kgs","178 Kgs","179 Kgs",
                "180 Kgs","181 Kgs","182 Kgs","183 Kgs","184 Kgs","185 Kgs","186 Kgs","187 Kgs","188 Kgs","189 Kgs",
                "190 Kgs","191 Kgs","192 Kgs","193 Kgs","194 Kgs","195 Kgs","196 Kgs","197 Kgs","198 Kgs","199 Kgs","200 Kgs"],
                "visible": 6
    },
    "Father Status": {
        "options": ["Alive","Passed Away"],
        "visible": 2
    },
    "Mother Status": {
        "options": ["Alive","Passed Away"],
        "visible": 2
    },
    "Sister": {
        "options": ["No Sister","1 Sister","2 Sisters","3 Sisters","4 Sisters"],
        "visible": 5
    },
    "Brother": {
        "options": ["No Brother","1 Brother","2 Brothers","3 Brothers","4 Brothers"],
        "visible": 5
    },
    "Children Boy": {
        "options": ["Not Applicable","No Boy Baby","1 Boy Baby","2 Boy Babies","3 Boy Babies","4 Boy Babies"],
        "visible": 6
    },
    "Children Girl": {
        "options": ["Not Applicable","No Girl Baby","1 Girl Baby","2 Girl Babies","3 Girl Babies","4 Girl Babies"],
        "visible": 6
    },
    "Emp Status": {
        "options": ["Not Working","Student","Private Company","business/self Employed","Government/ Public Sector",
                    "Defense/Civil Services"],
        "visible": 6
    },
    "Annual Income": {
        "options": ["Upto 1 Lakh","1 Lakh to 2 Lakh Annually","2 Lakh to 4 Lakh Annually","4 Lakh to 7 Lakh Annually",
                    "7 Lakh to 10 Lakh Annually","10 Lakh to 15 Lakh Annually","15 Lakh to 20 Lakh Annually",
                    "20 Lakh to 30 Lakh Annually","30 Lakh to 50 Lakh Annually","50 Lakh to 75 Lakh Annually",
                    "75 Lakh to 1 Core Annually","1 Core & Above Annually","Dont Like To Specify","Not Applicable"],
        "visible": 8
    }
}

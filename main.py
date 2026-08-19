courses = []

while True:
    course_name = input("Enter course name (or type 'done' to finish): ")
    
    if course_name.lower() == "done":
        break
    
    course_code = input("Enter course code: ")
    courses.append(f"{course_name} ({course_code})")
    print(f"You added {course_name} ({course_code}).")

print("\nHere are all your courses:")
for course in courses:
    print(course)

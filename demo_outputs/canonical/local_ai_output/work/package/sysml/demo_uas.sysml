package DemoUAS
part def Airframe
part def Battery
part def FlightController
part airframe : Airframe
part battery : Battery
part controller : FlightController
attribute battery_state
attribute vehicle_speed
action ReturnToBase

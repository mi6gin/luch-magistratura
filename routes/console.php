<?php

use Illuminate\Support\Facades\Schedule;

Schedule::call(fn () => null)->daily();

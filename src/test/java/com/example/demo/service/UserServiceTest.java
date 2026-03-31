package com.example.demo.service;

import com.example.demo.entity.User;
import com.example.demo.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import java.util.List;

import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class UserServiceTest {

    @Mock
    private UserRepository repo;

    @InjectMocks
    private UserService service;

    public UserServiceTest() {
        MockitoAnnotations.openMocks(this);
    }

    @Test
    void testCreateUser() {
        User user = new User(null, "Joshua", 21);

        when(repo.save(user)).thenReturn(new User(1L, "Joshua", 21));

        User saved = service.createUser(user);

        assertNotNull(saved.getId());
        assertEquals("Joshua", saved.getName());
    }

    @Test
    void testGetAllUsers() {
        when(repo.findAll()).thenReturn(
                List.of(new User(1L, "Josh", 21))
        );

        List<User> users = service.getAllUsers();

        assertEquals(1, users.size());
    }
}